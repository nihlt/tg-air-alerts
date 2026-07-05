import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from telethon import TelegramClient


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CHANNELS_PATH = BASE_DIR / "tg-chanel-links.txt"
EXPORTS_DIR = BASE_DIR / "exports"
PHOTOS_DIR = EXPORTS_DIR / "photos"
OUTPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
SESSION_PATH = BASE_DIR / "telegram_export"

KYIV_TZ = ZoneInfo("Europe/Kyiv")
START_KYIV = datetime(2026, 7, 1, 16, 0, tzinfo=KYIV_TZ)
END_KYIV = datetime(2026, 7, 2, 8, 0, tzinfo=KYIV_TZ)
START_UTC = START_KYIV.astimezone(timezone.utc)
END_UTC = END_KYIV.astimezone(timezone.utc)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def load_config() -> tuple[int, str, str | None, str | None]:
    config = dotenv_values(ENV_PATH)
    api_id = config.get("api_id")
    api_hash = config.get("api_hash")
    phone = config.get("phone") or config.get("tg_phone")
    bot_token = config.get("bot_token")

    if not api_id or not api_hash:
        raise RuntimeError(f"Missing api_id or api_hash in {ENV_PATH}")

    return int(api_id), api_hash, phone, bot_token


def prompt_for_phone(phone: str | None) -> str:
    if not phone:
        phone = input("Enter your Telegram phone number, e.g. +380XXXXXXXXX: ").strip()

    if phone.startswith("<") or not phone.startswith("+"):
        raise RuntimeError(
            "Invalid phone number. Use your Telegram account phone in international "
            "format, for example +380XXXXXXXXX. api_id/api_hash are already read from .env."
        )

    return phone


def load_channels() -> list[str]:
    if not CHANNELS_PATH.exists():
        raise RuntimeError(f"Channels file not found: {CHANNELS_PATH}")

    channels = [
        line.strip()
        for line in CHANNELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not channels:
        raise RuntimeError(f"No channels found in {CHANNELS_PATH}")

    return channels


def safe_folder_name(value: object, fallback: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", str(value or "").strip()).strip("._")
    return cleaned or fallback


def channel_folder_name(entity) -> str:
    channel_name = getattr(entity, "username", None) or getattr(entity, "title", None)
    fallback = f"channel_{getattr(entity, 'id', 'unknown')}"
    return safe_folder_name(channel_name, fallback)


def message_to_record(channel_url: str, message, photo_path: Path | None) -> dict:
    message_date_utc = message.date.astimezone(timezone.utc)
    replies = getattr(message, "replies", None)

    return {
        "channel": getattr(message.chat, "username", None) or getattr(message.chat, "title", None),
        "channel_url": channel_url,
        "message_id": message.id,
        "date_utc": message_date_utc.isoformat(),
        "date_kyiv": message_date_utc.astimezone(KYIV_TZ).isoformat(),
        "text": message.message or "",
        "views": message.views,
        "forwards": message.forwards,
        "replies": replies.replies if replies else None,
        "post_author": message.post_author,
        "grouped_id": str(message.grouped_id) if message.grouped_id else None,
        "has_media": message.media is not None,
        "photo_path": photo_path.as_posix() if photo_path else None,
    }


async def download_photo(message, channel_dir: Path, channel_url: str) -> Path | None:
    if not message.photo:
        return None

    channel_dir.mkdir(parents=True, exist_ok=True)
    target_path = channel_dir / f"{message.id}.jpg"

    try:
        downloaded_path = await message.download_media(file=target_path)
    except Exception as exc:
        print(f"[warn] {channel_url} message {message.id}: photo download failed: {exc}", file=sys.stderr)
        return None

    if not downloaded_path:
        return None

    return Path(downloaded_path).relative_to(BASE_DIR)


async def export_channel(client: TelegramClient, channel_url: str, output_file) -> int:
    entity = await client.get_entity(channel_url)
    channel_dir = PHOTOS_DIR / channel_folder_name(entity)
    exported_count = 0

    async for message in client.iter_messages(entity):
        message_date_utc = message.date.astimezone(timezone.utc)

        if message_date_utc >= END_UTC:
            continue

        if message_date_utc < START_UTC:
            break

        photo_path = await download_photo(message, channel_dir, channel_url)
        record = message_to_record(channel_url, message, photo_path)
        output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        exported_count += 1

    return exported_count


async def main() -> None:
    api_id, api_hash, phone, bot_token = load_config()
    channels = load_channels()
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    if bot_token:
        await client.start(bot_token=bot_token)
    else:
        await client.start(phone=prompt_for_phone(phone))

    try:
        total_exported = 0

        with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as output_file:
            for channel_url in channels:
                try:
                    count = await export_channel(client, channel_url, output_file)
                except Exception as exc:
                    print(f"[warn] {channel_url}: {exc}", file=sys.stderr)
                    continue

                total_exported += count
                print(f"[ok] {channel_url}: exported {count} posts")
    finally:
        await client.disconnect()

    print(f"Done. Exported {total_exported} posts to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
