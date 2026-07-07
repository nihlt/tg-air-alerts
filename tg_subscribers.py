from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

from tg_data import BASE_DIR

logger = logging.getLogger(__name__)
KYIV_TZ = ZoneInfo("Europe/Kyiv")
SUBSCRIBERS_PATH = BASE_DIR / "tg_subscribers.json"
ENV_PATH = BASE_DIR / ".env"


@dataclass(frozen=True)
class Subscriber:
    chat_id: str
    username: str | None
    forward_noise: bool
    registered_at: str


def _empty_data() -> dict[str, Any]:
    return {"users": {}}


def load_subscribers_data(path: Path = SUBSCRIBERS_PATH) -> dict[str, Any]:
    if not path.exists():
        return _empty_data()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("users"), dict):
            return _empty_data()
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Invalid subscribers config, starting fresh")
        return _empty_data()


def save_subscribers_data(data: dict[str, Any], path: Path = SUBSCRIBERS_PATH) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _subscriber_from_entry(chat_id: str, entry: dict[str, Any]) -> Subscriber:
    return Subscriber(
        chat_id=str(chat_id),
        username=entry.get("username"),
        forward_noise=bool(entry.get("forward_noise", False)),
        registered_at=str(entry.get("registered_at") or ""),
    )


def list_subscribers(path: Path = SUBSCRIBERS_PATH) -> list[Subscriber]:
    data = load_subscribers_data(path)
    return [
        _subscriber_from_entry(chat_id, entry)
        for chat_id, entry in data.get("users", {}).items()
    ]


def subscribers_with_noise(path: Path = SUBSCRIBERS_PATH) -> list[Subscriber]:
    return [sub for sub in list_subscribers(path) if sub.forward_noise]


def is_subscriber(chat_id: str, path: Path = SUBSCRIBERS_PATH) -> bool:
    data = load_subscribers_data(path)
    return str(chat_id) in data.get("users", {})


def register_user(
    chat_id: str,
    username: str | None = None,
    *,
    path: Path = SUBSCRIBERS_PATH,
) -> Subscriber:
    data = load_subscribers_data(path)
    users = data.setdefault("users", {})
    key = str(chat_id)
    now = datetime.now(KYIV_TZ).isoformat(timespec="seconds")
    existing = users.get(key, {})
    users[key] = {
        "username": username or existing.get("username"),
        "forward_noise": bool(existing.get("forward_noise", False)),
        "registered_at": existing.get("registered_at") or now,
    }
    save_subscribers_data(data, path)
    return _subscriber_from_entry(key, users[key])


def set_forward_noise(
    chat_id: str,
    enabled: bool,
    *,
    path: Path = SUBSCRIBERS_PATH,
) -> Subscriber:
    data = load_subscribers_data(path)
    users = data.setdefault("users", {})
    key = str(chat_id)
    if key not in users:
        register_user(key, path=path)
        data = load_subscribers_data(path)
        users = data["users"]
    users[key]["forward_noise"] = enabled
    save_subscribers_data(data, path)
    return _subscriber_from_entry(key, users[key])


def toggle_forward_noise(chat_id: str, *, path: Path = SUBSCRIBERS_PATH) -> tuple[Subscriber, str]:
    data = load_subscribers_data(path)
    users = data.setdefault("users", {})
    key = str(chat_id)
    if key not in users:
        register_user(key, path=path)
        data = load_subscribers_data(path)
        users = data["users"]
    enabled = not bool(users[key].get("forward_noise", False))
    users[key]["forward_noise"] = enabled
    save_subscribers_data(data, path)
    sub = _subscriber_from_entry(key, users[key])
    reply = "Шумні пости: надсилати" if enabled else "Шумні пости: ігнорувати"
    return sub, reply


def ensure_author_subscriber(path: Path = SUBSCRIBERS_PATH) -> None:
    if list_subscribers(path):
        return
    config = dotenv_values(ENV_PATH)
    author_id = (config.get("TELEGRAM_AUTHOR") or config.get("telegram_user_id") or "").strip()
    if not author_id:
        return
    register_user(author_id, path=path)
    logger.info("Seeded subscriber from TELEGRAM_AUTHOR: %s", author_id)
