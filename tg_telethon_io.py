from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from telethon import TelegramClient
from telethon.sessions import StringSession

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
CHANNELS_PATH = BASE_DIR / "tg-chanel-links.txt"
EXPORTS_DIR = BASE_DIR / "exports"
PHOTOS_DIR = EXPORTS_DIR / "photos"
LIVE_JSONL_PATH = EXPORTS_DIR / "tg_posts_live.jsonl"

# Plain-text Telethon session (no SQLite, no file locking).
SESSION_STRING_PATH = BASE_DIR / "telegram_session.txt"
# Old SQLite session from earlier versions — migrated once, then optional to delete.
LEGACY_SQLITE_SESSION_PATH = BASE_DIR / "telegram_export"

KYIV_TZ = ZoneInfo("Europe/Kyiv")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")

_jsonl_lock = threading.Lock()


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


def load_session_string() -> str | None:
    if not SESSION_STRING_PATH.exists():
        return None
    value = SESSION_STRING_PATH.read_text(encoding="utf-8").strip()
    return value or None


def save_session_string(client: TelegramClient) -> None:
    value = StringSession.save(client.session)
    if not value:
        raise RuntimeError("Failed to export Telethon session string")
    SESSION_STRING_PATH.write_text(value, encoding="utf-8")


def _legacy_sqlite_exists() -> bool:
    return LEGACY_SQLITE_SESSION_PATH.with_suffix(".session").exists()


async def create_telegram_client() -> TelegramClient:
    api_id, api_hash, phone, bot_token = load_config()

    session_text = load_session_string()
    if session_text is None:
        if _legacy_sqlite_exists():
            raise RuntimeError(
                "Found old telegram_export.session (SQLite — causes file locks). "
                "Run once: python migrate_telegram_session.py"
            )
        session = StringSession()
    else:
        session = StringSession(session_text)

    client = TelegramClient(session, api_id, api_hash)
    if bot_token:
        await client.start(bot_token=bot_token)
    else:
        await client.start(phone=prompt_for_phone(phone))

    save_session_string(client)
    return client


def load_channels() -> list[str]:
    if not CHANNELS_PATH.exists():
        raise RuntimeError(f"Channels file not found: {CHANNELS_PATH}")

    seen: set[str] = set()
    channels: list[str] = []
    for line in CHANNELS_PATH.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        if url in seen:
            continue
        seen.add(url)
        channels.append(url)

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


def message_to_record(
    channel_url: str,
    message,
    photo_path: Path | None,
    *,
    channel_name: str | None = None,
) -> dict:
    message_date_utc = message.date.astimezone(timezone.utc)
    replies = getattr(message, "replies", None)
    if channel_name is None:
        channel_name = getattr(message.chat, "username", None) or getattr(message.chat, "title", None)

    return {
        "channel": channel_name,
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


def append_jsonl(path: Path, record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _jsonl_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as output_file:
            output_file.write(line)
            output_file.flush()


def ensure_export_dirs() -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
