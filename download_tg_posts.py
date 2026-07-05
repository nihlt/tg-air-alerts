import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telethon import TelegramClient


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CHANNELS_PATH = BASE_DIR / "tg-chanel-links.txt"
EXPORTS_DIR = BASE_DIR / "exports"
PHOTOS_DIR = EXPORTS_DIR / "photos"
OUTPUT_PATH = EXPORTS_DIR / "tg_posts_2026-07-06_0140_to_2026-07-06_0240.jsonl"
SESSION_PATH = BASE_DIR / "telegram_export"

KYIV_TZ = ZoneInfo("Europe/Kyiv")
START_KYIV = datetime(2026, 7, 6, 1, 40, tzinfo=KYIV_TZ)
END_KYIV = datetime(2026, 7, 6, 2, 40, tzinfo=KYIV_TZ)
START_UTC = START_KYIV.astimezone(timezone.utc)
END_UTC = END_KYIV.astimezone(timezone.utc)
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def load_config() -> tuple[int, str, str | None, str | None]:
    load_dotenv(ENV_PATH)
    
    api_id = os.environ.get("api_id") or os.environ.get("API_ID")
    api_hash = os.environ.get("api_hash") or os.environ.get("API_HASH")
    phone = os.environ.get("phone") or os.environ.get("tg_phone") or os.environ.get("PHONE")
    bot_token = os.environ.get("bot_token") or os.environ.get("BOT_TOKEN")

    if not api_id or not api_hash:
        raise RuntimeError(
            f"Missing api_id or api_hash in environment or {ENV_PATH}.\n"
            "Please specify them in your environment variables or enter them in your .env file."
        )

    try:
        api_id_int = int(api_id)
    except ValueError:
        raise RuntimeError(
            f"api_id must be a valid integer number (e.g., 123456). Got: {api_id!r}"
        )

    return api_id_int, api_hash, phone, bot_token


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


async def custom_code_callback() -> str:
    code_path = BASE_DIR / "code.txt"
    print(f"[info] Waiting up to 30 seconds for Telegram login code to be written into '{code_path.name}'...", flush=True)
    
    for _ in range(30):
        if code_path.exists():
            try:
                content = code_path.read_text(encoding="utf-8").strip()
                if content:
                    print(f"[info] Successfully read code from {code_path.name}", flush=True)
                    code_path.unlink(missing_ok=True)
                    return content
            except Exception as exc:
                print(f"[warn] Failed to read/delete {code_path.name}: {exc}", flush=True)
        await asyncio.sleep(1)

    if sys.stdin.isatty():
        return input("Please enter the code you received: ").strip()

    raise RuntimeError(
        f"Timed out waiting for code.txt in {BASE_DIR}.\n"
        "Please write the Telegram verification code into that file."
    )


async def main() -> None:
    api_id, api_hash, phone, bot_token = load_config()
    channels = load_channels()
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    if bot_token:
        await client.start(bot_token=bot_token)
    else:
        await client.start(phone=prompt_for_phone(phone), code_callback=custom_code_callback)

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
