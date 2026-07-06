from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import ChannelPrivateError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.types import Channel

from tg_format import escape_html
from tg_listener_process import acquire_listener_lock, release_listener_lock
from tg_send import SEND_PAUSE_SECONDS, TelegramBot, load_bot_config
from tg_telethon_io import (
    BASE_DIR,
    LIVE_JSONL_PATH,
    PHOTOS_DIR,
    append_jsonl,
    channel_folder_name,
    create_telegram_client,
    download_photo,
    ensure_export_dirs,
    load_channels,
    message_to_record,
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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
    ) -> None:
        self.client = client
        self.bot = bot
        self.jsonl_path = jsonl_path
        self.channel_urls: dict[int, str] = {}
        self.entities: list[Channel] = []
        self.joined_in_session: list[Channel] = []
        self._stopped = False

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
                await self.client(JoinChannelRequest(entity))
                self.joined_in_session.append(entity)
                logger.info("Joined %s", channel_url)
            except UserAlreadyParticipantError:
                logger.info("Already in %s", channel_url)
            except ChannelPrivateError:
                logger.warning("Skip %s: private channel, invite required", channel_url)
                continue
            except Exception as exc:
                logger.warning("Skip %s: join failed: %s", channel_url, exc)
                continue

            self.channel_urls[entity.id] = channel_url
            self.entities.append(entity)

        if not self.entities:
            raise RuntimeError("No channels available for listening")

        logger.info("Listening to %s channels", len(self.entities))

    def _channel_url_for(self, chat_id: int) -> str:
        return self.channel_urls.get(chat_id, f"https://t.me/c/{chat_id}")

    async def handle_message(self, event: events.NewMessage.Event) -> None:
        message = event.message
        chat = await event.get_chat()
        chat_id = event.chat_id
        if chat_id is None:
            return

        channel_url = self._channel_url_for(chat_id)
        channel_dir = PHOTOS_DIR / channel_folder_name(chat)
        photo_path = await download_photo(message, channel_dir, channel_url)
        record = message_to_record(channel_url, message, photo_path)
        append_jsonl(self.jsonl_path, record)

        caption = format_live_message(record)
        logger.info(
            "New post %s:%s",
            record.get("channel"),
            record.get("message_id"),
        )

        try:
            if photo_path is not None:
                absolute_path = BASE_DIR / photo_path
                self.bot.send_photo(absolute_path, caption=caption)
            else:
                self.bot.send_message(caption)
        except Exception:
            logger.exception(
                "Failed to forward %s:%s",
                record.get("channel"),
                record.get("message_id"),
            )
            return

        time.sleep(SEND_PAUSE_SECONDS)

    async def leave_session_channels(self) -> None:
        for entity in self.joined_in_session:
            channel_url = self.channel_urls.get(entity.id, str(entity.id))
            try:
                await self.client(LeaveChannelRequest(entity))
                logger.info("Left %s", channel_url)
            except Exception as exc:
                logger.warning("Failed to leave %s: %s", channel_url, exc)
        self.joined_in_session.clear()

    async def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        await self.leave_session_channels()
        if self.client.is_connected():
            await self.client.disconnect()

    async def run(self) -> None:
        channel_urls = load_channels()
        ensure_export_dirs()
        await self.setup_channels(channel_urls)

        @self.client.on(events.NewMessage(chats=self.entities))
        async def on_new_message(event: events.NewMessage.Event) -> None:
            if self._stopped:
                return
            try:
                await self.handle_message(event)
            except Exception:
                logger.exception("Failed to handle incoming message")

        logger.info("Live listener running. Press Ctrl+C to stop.")
        await self.client.run_until_disconnected()


async def run_listener(*, jsonl_path: Path = LIVE_JSONL_PATH) -> None:
    acquire_listener_lock()
    try:
        token, author_id = load_bot_config()
        bot = TelegramBot(token, author_id)
        client = await create_telegram_client()
        listener = LiveChannelListener(client=client, bot=bot, jsonl_path=jsonl_path)

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
    args = parser.parse_args()
    asyncio.run(run_listener(jsonl_path=args.jsonl_path))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(0)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
