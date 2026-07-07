from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events, utils
from telethon.errors import ChannelPrivateError, UserAlreadyParticipantError, UserNotParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.types import Channel

from tg_bot_handlers import LiveListenerState, process_live_bot_update
from tg_data import post_key
from tg_format import escape_html, format_channel_link, strip_subscribe_footer
from tg_listener_process import acquire_listener_lock, release_listener_lock
from tg_live_events import IngestKind, LiveEventEngine
from tg_rating import build_rating_keyboard
from tg_send import SEND_PAUSE_SECONDS, TelegramBot, broadcast_alert, load_bot_config, send_event_alert, send_summary_alert
from tg_subscribers import ensure_author_subscriber, list_subscribers, subscribers_with_noise
from tg_telethon_io import (
    BASE_DIR,
    LIVE_JSONL_PATH,
    PHOTOS_DIR,
    append_jsonl,
    channel_folder_name,
    create_telegram_client,
    download_photo,
    ensure_export_dirs,
    is_ad_message,
    load_channels,
    message_to_record,
    load_channel_stances,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

KYIV_TZ = ZoneInfo("Europe/Kyiv")
FLUSH_INTERVAL_SECONDS = 5


def format_live_message(record: dict, stances: dict[str, str] | None = None) -> str:
    channel = record.get("channel") or "unknown"
    message_id = record.get("message_id")
    date_kyiv = str(record.get("date_kyiv") or "")
    time_part = date_kyiv[11:16] if len(date_kyiv) >= 16 else date_kyiv
    text = strip_subscribe_footer(str(record.get("text") or "").strip()) or "(без тексту)"
    
    # Resolve stance emoji
    stance = ""
    if stances:
        clean_url = str(record.get("channel_url") or "").rstrip("/")
        for curl, cstance in stances.items():
            if curl.rstrip("/") == clean_url:
                stance = cstance
                break

    channel_label = f"@{channel}" if channel and not str(channel).startswith("@") else str(channel)
    channel_header = format_channel_link(record) if channel != "unknown" else escape_html(channel_label)
    
    if stance:
        header = f"{channel_header} · {stance} · {escape_html(time_part)}"
    else:
        header = f"{channel_header} · {escape_html(time_part)}"

    return (
        f"{header}\n\n"
        f"{escape_html(text)}"
    )


class LiveChannelListener:
    def __init__(
        self,
        *,
        client: TelegramClient,
        bot: TelegramBot,
        jsonl_path: Path = LIVE_JSONL_PATH,
        leave_on_exit: bool = False,
    ) -> None:
        self.client = client
        self.bot = bot
        self.jsonl_path = jsonl_path
        self.leave_on_exit = leave_on_exit
        self.author_chat_id = str(bot.chat_id)
        self.api_bot = TelegramBot(bot.token)
        self.channel_urls: dict[int, str] = {}
        self.entities_by_chat_id: dict[int, Channel] = {}
        self.entities: list[Channel] = []
        self.joined_in_session: list[Channel] = []
        self.engine = LiveEventEngine()
        self.posts_index: dict[str, dict] = {}
        self.state = LiveListenerState.load()
        self._stopped = False
        self._message_lock = asyncio.Lock()
        self._post_buffers: dict[str, list[tuple[dict, Path | None]]] = {}

    async def setup_channels(self, channel_urls: list[str]) -> None:
        for channel_url in channel_urls:
            try:
                entity = await self.client.get_entity(channel_url)
            except Exception as exc:
                logger.warning("Skip %s: cannot resolve entity: %s", channel_url, exc)
                continue

            if not isinstance(entity, Channel):
                logger.warning("Skip %s: not a channel", channel_url)
                continue

            try:
                if getattr(entity, "left", True):
                    await self.client(JoinChannelRequest(entity))
                    self.joined_in_session.append(entity)
                    logger.info("Joined %s", channel_url)
                else:
                    logger.info("Already in %s (skipped join)", channel_url)
            except UserAlreadyParticipantError:
                logger.info("Already in %s", channel_url)
            except ChannelPrivateError:
                logger.warning("Skip %s: private channel, invite required", channel_url)
                continue
            except Exception as exc:
                logger.warning("Skip %s: join failed: %s", channel_url, exc)
                continue

            chat_id = utils.get_peer_id(entity)
            self.channel_urls[chat_id] = channel_url
            self.entities_by_chat_id[chat_id] = entity
            self.entities.append(entity)

        if not self.entities:
            raise RuntimeError("No channels available for listening")

        logger.info("Listening to %s channels", len(self.entities))

    def _channel_url_for(self, chat_id: int) -> str:
        return self.channel_urls.get(chat_id, f"https://t.me/c/{chat_id}")

    def _entity_for(self, chat_id: int | None) -> Channel | None:
        if chat_id is None:
            return None
        return self.entities_by_chat_id.get(chat_id)

    async def _enqueue_post(self, record: dict, photo_path: Path | None) -> None:
        grouped_id = record.get("grouped_id")
        if not grouped_id:
            await self._forward_post_batch([(record, photo_path)])
            return

        gid = str(grouped_id)
        if gid not in self._post_buffers:
            self._post_buffers[gid] = []
            asyncio.create_task(self._flush_post_group(gid))
        self._post_buffers[gid].append((record, photo_path))

    async def _flush_post_group(self, gid: str) -> None:
        await asyncio.sleep(1.5)
        items = self._post_buffers.pop(gid, [])
        if items:
            await self._forward_post_batch(items)

    async def _forward_post_batch(self, items: list[tuple[dict, Path | None]]) -> None:
        stances = load_channel_stances()
        texts = []
        photos = []
        main_record = items[0][0]
        
        for record, photo_path in items:
            text = record.get("text", "").strip()
            if text:
                texts.append(text)
            if photo_path:
                photos.append((photo_path, record.get("channel"), record.get("message_id")))

        combined_text = "\n\n".join(texts) if texts else ""
        record_copy = dict(main_record)
        record_copy["text"] = combined_text
        caption = format_live_message(record_copy, stances=stances)

        subscribers = list_subscribers()
        if not subscribers:
            return

        from tg_send import PhotoItem
        # Build rating keyboard using the first post's key
        key = post_key(main_record.get("channel"), main_record.get("message_id"))
        keyboard = build_rating_keyboard(key)

        for sub in subscribers:
            bot = self.api_bot.for_chat(sub.chat_id)
            if photos:
                if len(photos) == 1:
                    absolute_path = BASE_DIR / photos[0][0]
                    await asyncio.to_thread(bot.send_photo, absolute_path)
                else:
                    photo_items = [
                        PhotoItem(
                            path=BASE_DIR / p[0],
                            channel=p[1],
                            message_id=p[2],
                        )
                        for p in photos
                    ]
                    await asyncio.to_thread(bot.send_media_group, photo_items)
            await asyncio.to_thread(bot.send_message, caption, reply_markup=keyboard)
            await asyncio.sleep(SEND_PAUSE_SECONDS)

    async def handle_message(self, event: events.NewMessage.Event) -> None:
        async with self._message_lock:
            message = event.message
            chat_id = event.chat_id
            if chat_id is None:
                return

            entity = self._entity_for(chat_id)
            channel_url = self._channel_url_for(chat_id)

            if is_ad_message(message, channel_url):
                logger.info(
                    "Skip post %s:%s: classified as ad",
                    getattr(entity, "username", None) or getattr(entity, "title", None) or chat_id,
                    message.id
                )
                return

            channel_name = None
            if entity is not None:
                channel_name = getattr(entity, "username", None) or getattr(entity, "title", None)
                channel_dir = PHOTOS_DIR / channel_folder_name(entity)
            else:
                channel_dir = PHOTOS_DIR / f"channel_{chat_id}"

            photo_path = await download_photo(message, channel_dir, channel_url)
            record = message_to_record(
                channel_url,
                message,
                photo_path,
                channel_name=channel_name,
            )
            append_jsonl(self.jsonl_path, record)

            key = post_key(record.get("channel"), record.get("message_id"))
            self.posts_index[key] = record

            result = self.engine.ingest(record)
            logger.info(
                "New post %s:%s -> %s",
                record.get("channel"),
                record.get("message_id"),
                result.kind.value,
            )

            if result.kind == IngestKind.EMPTY:
                return

            try:
                await self._enqueue_post(record, photo_path)
            except Exception:
                logger.exception(
                    "Failed to forward post %s:%s",
                    record.get("channel"),
                    record.get("message_id"),
                )

    async def flush_loop(self) -> None:
        while not self._stopped:
            try:
                now = datetime.now(KYIV_TZ)
                for thread in self.engine.ready_threads(now):
                    self.engine.mark_sent(thread.id)
                    logger.info("Processed live event %s silently (individual posts already forwarded)", thread.id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Flush loop error")
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)

    async def bot_updates_loop(self) -> None:
        while not self._stopped:
            try:
                updates = await asyncio.to_thread(
                    self.api_bot.get_updates,
                    offset=self.state.update_offset,
                    timeout=30,
                )
                for update in updates:
                    await asyncio.to_thread(
                        process_live_bot_update,
                        self.api_bot,
                        bot=self.bot,
                        state=self.state,
                    )
                    self.state.save()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Bot updates loop error")
                await asyncio.sleep(1)

    async def leave_listening_channels(self) -> None:
        for entity in self.entities:
            chat_id = utils.get_peer_id(entity)
            channel_url = self.channel_urls.get(chat_id, str(entity.id))
            try:
                await self.client(LeaveChannelRequest(entity))
                logger.info("Left %s", channel_url)
            except UserNotParticipantError:
                logger.info("Not subscribed to %s", channel_url)
            except Exception as exc:
                logger.warning("Failed to leave %s: %s", channel_url, exc)
        self.joined_in_session.clear()

    async def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.state.save()
        if self.leave_on_exit:
            await self.leave_listening_channels()
        if self.client.is_connected():
            await self.client.disconnect()

    async def run(self) -> None:
        channel_urls = load_channels()
        ensure_export_dirs()
        ensure_author_subscriber()
        await self.setup_channels(channel_urls)

        subscriber_count = len(list_subscribers())
        logger.info("Subscribers: %s (/start to register, /toggle for noise)", subscriber_count)

        flush_task = asyncio.create_task(self.flush_loop())
        updates_task = asyncio.create_task(self.bot_updates_loop())

        @self.client.on(events.NewMessage(chats=self.entities))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            if self._stopped:
                return
            try:
                await self.handle_message(event)
            except Exception:
                logger.exception("Failed to handle incoming message")

        logger.info("Live listener running. Press Ctrl+C to stop.")
        try:
            await self.client.run_until_disconnected()
        finally:
            flush_task.cancel()
            updates_task.cancel()
            for task in (flush_task, updates_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self.state.save()


async def run_listener(*, jsonl_path: Path = LIVE_JSONL_PATH, leave_on_exit: bool = False) -> None:
    acquire_listener_lock()
    try:
        token, author_id = load_bot_config()
        bot = TelegramBot(token, author_id)
        client = await create_telegram_client()
        listener = LiveChannelListener(client=client, bot=bot, jsonl_path=jsonl_path, leave_on_exit=leave_on_exit)

        try:
            await listener.run()
        finally:
            await listener.shutdown()
    finally:
        release_listener_lock()


def main() -> None:
    parser = argparse.ArgumentParser(description="Listen to Telegram channels and forward posts via bot.")
    parser.add_argument(
        "--jsonl-path",
        type=Path,
        default=LIVE_JSONL_PATH,
        help=f"Append live posts to this jsonl file (default: {LIVE_JSONL_PATH.name})",
    )
    parser.add_argument(
        "--leave-on-exit",
        action="store_true",
        help="Leave all monitored channels when exiting",
    )
    args = parser.parse_args()
    asyncio.run(run_listener(jsonl_path=args.jsonl_path, leave_on_exit=args.leave_on_exit))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(0)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
