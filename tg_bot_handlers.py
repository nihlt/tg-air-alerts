from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tg_data import BASE_DIR
from tg_rating import build_rating_keyboard, log_rating, parse_rating_callback
from tg_send import TelegramBot
from tg_subscribers import (
    is_subscriber,
    register_user,
    toggle_forward_noise,
)

logger = logging.getLogger(__name__)

LIVE_STATE_PATH = BASE_DIR / "exports" / "live_listener_state.json"

WELCOME_TEXT = """<b>tg-air-alerts</b>

Ви підписані на live-алерти.

<b>Команди</b>
<code>/toggle</code> — увімкнути/вимкнути шумні пости (неподії з каналів)"""


@dataclass
class LiveListenerState:
    update_offset: int | None = None

    @classmethod
    def load(cls, path: Path = LIVE_STATE_PATH) -> LiveListenerState:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(update_offset=data.get("update_offset"))
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Invalid live listener state, starting fresh")
            return cls()

    def save(self, path: Path = LIVE_STATE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"update_offset": self.update_offset}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )


def is_toggle_command(text: str) -> bool:
    normalized = text.strip().lower().split("@", 1)[0]
    return normalized in {"/toggle", "toggle"}


def is_start_command(text: str) -> bool:
    normalized = text.strip().lower().split("@", 1)[0]
    return normalized in {"/start", "start"}


def apply_rating_callback(
    bot: TelegramBot,
    *,
    chat_id: str,
    data: str,
    bot_message_id: int,
    user_id: int | str,
    username: str | None,
) -> str | None:
    parsed = parse_rating_callback(data)
    if parsed.action == "noop":
        return None
    if parsed.action != "vote" or not parsed.rating or not parsed.item_id:
        return "Невідома дія."

    log_rating(
        user_id=user_id,
        username=username,
        chat_id=chat_id,
        item_id=parsed.item_id,
        rating=parsed.rating,
        bot_message_id=bot_message_id,
    )
    bot.for_chat(chat_id).edit_message_reply_markup(
        bot_message_id,
        reply_markup=build_rating_keyboard(parsed.item_id, voted=parsed.rating),
    )
    return "Збережено"


def process_live_bot_update(
    api_bot: TelegramBot,
    update: dict[str, Any],
    *,
    state: LiveListenerState,
) -> None:
    update_id = int(update.get("update_id", 0))
    state.update_offset = update_id + 1

    callback = update.get("callback_query")
    if callback:
        _process_callback(api_bot, callback)
        return

    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    from_user = message.get("from") or {}
    username = from_user.get("username")

    text = message.get("text")
    if not text:
        return

    if is_start_command(text):
        register_user(chat_id, username)
        api_bot.for_chat(chat_id).send_message(WELCOME_TEXT)
        return

    if not is_subscriber(chat_id):
        return

    if is_toggle_command(text):
        _, reply = toggle_forward_noise(chat_id)
        api_bot.for_chat(chat_id).send_message(reply)


def _process_callback(
    api_bot: TelegramBot,
    callback: dict[str, Any],
) -> None:
    callback_id = str(callback.get("id", ""))
    data = str(callback.get("data") or "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not is_subscriber(chat_id):
        api_bot.answer_callback_query(callback_id)
        return

    try:
        message_id = message.get("message_id")
        from_user = callback.get("from") or {}
        if message_id is not None and data.startswith("rate:"):
            notice = apply_rating_callback(
                api_bot,
                chat_id=chat_id,
                data=data,
                bot_message_id=int(message_id),
                user_id=from_user.get("id", 0),
                username=from_user.get("username"),
            )
        else:
            notice = "Невідома дія."
        if notice:
            api_bot.answer_callback_query(callback_id, text=notice)
        else:
            api_bot.answer_callback_query(callback_id)
    except Exception:
        logger.exception("Failed to handle callback %s", data)
        api_bot.answer_callback_query(callback_id, text="Помилка обробки.")
