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
from tg_format import escape_html
from tg_listener_process import acquire_listener_lock, release_listener_lock
from tg_live_events import IngestKind, LiveEventEngine
from tg_rating import build_rating_keyboard
from tg_send import SEND_PAUSE_SECONDS, TelegramBot, load_bot_config, send_event_alert, send_summary_alert
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
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
KYIV_TZ = ZoneInfo("Europe/Kyiv")
FLUSH_INTERVAL_SECONDS = 5


def format_live_message(record: dict) -> str:
    channel = record.get("channel") or "unknown"
    message_id = record.get("message_id")
    date_kyiv = str(record.get("date_kyiv") or "")
    time_part = date_kyiv[11:16] if len(date_kyiv) >= 16 else date_kyiv
    text = record.get("text") or "(без тексту)"
    channel_label = f"@{channel}" if channel and not str(channel).startswith("@") else str(channel)
    return (
        f"<b>{escape_html(channel_label)}</b> · {escape_html(time_part)}\n"
        f"<code>{escape_html(channel)}:{message_id}</code>\n\n"
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

    async def _forward_noise_post(self, record: dict, photo_path: Path | None) -> None:
        caption = format_live_message(record)
        if photo_path is not None:
            absolute_path = BASE_DIR / photo_path
            await asyncio.to_thread(self.bot.send_photo, absolute_path, caption=caption)
        else:
            await asyncio.to_thread(self.bot.send_message, caption)
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
                if result.kind == IngestKind.SUMMARY:
                    keyboard = build_rating_keyboard(key)
                    await asyncio.to_thread(
                        send_summary_alert,
                        self.bot,
                        record,
                        self.posts_index,
                        reply_markup=keyboard,
                    )
                    await asyncio.sleep(SEND_PAUSE_SECONDS)
                    return

                if result.kind == IngestKind.IGNORED:
                    if self.state.forward_noise:
                        await self._forward_noise_post(record, photo_path)
                    return

            except Exception:
                logger.exception(
                    "Failed to send alert for %s:%s",
                    record.get("channel"),
                    record.get("message_id"),
                )

    async def flush_loop(self) -> None:
        while not self._stopped:
            try:
                now = datetime.now(KYIV_TZ)
                for thread in self.engine.ready_threads(now):
                    event = self.engine.thread_to_event(thread)
                    keyboard = build_rating_keyboard(event["id"])
                    await asyncio.to_thread(
                        send_event_alert,
                        self.bot,
                        event,
                        self.posts_index,
                        reply_markup=keyboard,
                    )
                    self.engine.mark_sent(thread.id)
                    logger.info("Sent live event %s", thread.id)
                    await asyncio.sleep(SEND_PAUSE_SECONDS)
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
                        update,
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
        await self.setup_channels(channel_urls)

        noise_mode = "надсилати" if self.state.forward_noise else "ігнорувати"
        logger.info("Noise posts: %s (/toggle to switch)", noise_mode)

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
