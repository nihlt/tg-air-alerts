from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tg_data import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_JSONL_PATH,
    TimelineItem,
    build_timeline,
    find_index_by_event_id,
    find_index_by_item_id,
    find_nearest_index,
    load_events,
    load_posts,
    load_posts_index,
    normalize_event_id,
)
from tg_bot_handlers import apply_rating_callback
from tg_rating import build_rating_keyboard
from tg_send import TelegramBot, load_bot_token, send_event_alert, send_summary_alert

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "exports" / "debug_state.json"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

def build_help_text(event_range_hint: str) -> str:
    return f"""<b>Ласкаво просимо в debug-бот tg-air-alerts</b>

Тут можна переглядати згруповані події та summary-пости з експорту — так само, як на сайті, але в Telegram.

<b>Як це працює</b>
<b>Кнопки оцінки</b>
<i>під текстовим алертом: bullshit (зліва) або valuable (справа). Після вибору кнопка показує 🚫 або ✅</i>

<b>Листання</b>
<code>n</code> або <code>next</code>
<i>наступна подія або summary-пост у таймлайні</i>

<code>p</code> або <code>prev</code>
<i>попередня подія або summary-пост</i>

<b>Поточний алерт</b>
<code>/events</code>
<i>показати знову те, на чому ти зараз стоїш у таймлайні</i>

<b>Стрибок за id події</b>
<code>/goto evt_0048</code>
<i>перейти до конкретної події; можна без нулів: evt_48</i>

<b>Стрибок до summary-поста</b>
<code>/goto eRadarrua:98922</code>
<i>перейти до білого зведення за ключем канал:message_id</i>

<b>Стрибок за датою й часом</b>
<code>2026-07-02 02:15</code>
<i>перейти до найближчої події або summary-поста відповідно до цієї дати й часу (київський час)</i>

<b>Стрибок лише за часом</b>
<code>02:15</code>
<i>перейти до найближчого item у той самий день, що й поточна позиція в таймлайні</i>

<b>Довідка</b>
<code>/start</code> або <code>/help</code>
<i>показати це повідомлення знову</i>

{event_range_hint}"""

DATE_TIME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{1,2}-\d{1,2})\s+(?P<hour>\d{1,2})[:\.](?P<minute>\d{2})$"
)
TIME_ONLY_RE = re.compile(r"^(?P<hour>\d{1,2})[:\.](?P<minute>\d{2})$")
GOTO_RE = re.compile(r"^/goto(?:@\w+)?\s+(?P<target>.+)$", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class DebugSession:
    def __init__(
        self,
        chat_id: str,
        bot: TelegramBot,
        timeline: list[TimelineItem],
        posts_index: dict[str, dict[str, Any]],
        *,
        index: int = 0,
    ) -> None:
        self.chat_id = str(chat_id)
        self.bot = bot.for_chat(self.chat_id)
        self.timeline = timeline
        self.posts_index = posts_index
        self.index = index

    def event_id_range_hint(self) -> str:
        event_ids = [item.item_id for item in self.timeline if item.kind == "event"]
        if not event_ids:
            return "<i>Подій у таймлайні немає.</i>"
        return (
            f"<i>У датасеті {len(event_ids)} подій: "
            f"{event_ids[0]} … {event_ids[-1]}. У таймлайні також є summary-пости.</i>"
        )

    def send_help(self) -> None:
        hint = self.event_id_range_hint()
        self.bot.send_message(build_help_text(hint))

    def current_item(self) -> TimelineItem | None:
        if not self.timeline:
            return None
        self.index = max(0, min(self.index, len(self.timeline) - 1))
        return self.timeline[self.index]

    def show_current(self) -> None:
        item = self.current_item()
        if item is None:
            self.bot.send_message("Таймлайн порожній.")
            return

        debug_meta = (item, self.index, len(self.timeline))
        keyboard = build_rating_keyboard(item.item_id)
        if item.kind == "event" and item.event:
            send_event_alert(
                self.bot,
                item.event,
                self.posts_index,
                debug=True,
                debug_meta=debug_meta,
                reply_markup=keyboard,
            )
        elif item.summary_post:
            send_summary_alert(
                self.bot,
                item.summary_post,
                self.posts_index,
                debug=True,
                debug_meta=debug_meta,
                reply_markup=keyboard,
            )

    def move(self, delta: int) -> str | None:
        if not self.timeline:
            return "Таймлайн порожній."
        new_index = self.index + delta
        if new_index < 0:
            return "Початок списку."
        if new_index >= len(self.timeline):
            return "Кінець списку."
        self.index = new_index
        self.show_current()
        return None

    def goto_target(self, target: str) -> str | None:
        target = target.strip()

        moment = self.parse_datetime_input(target)
        if moment is not None:
            self.goto_datetime(moment)
            return None

        index = find_index_by_event_id(self.timeline, target)
        if index is None:
            index = find_index_by_item_id(self.timeline, target)
        if index is None:
            if target.lower().startswith("evt_"):
                return f"Не знайдено: {normalize_event_id(target)}. {self.event_id_range_hint()}"
            return f"Не знайдено: {target}"
        self.index = index
        self.show_current()
        return None

    def goto_datetime(self, moment: datetime) -> None:
        self.index = find_nearest_index(self.timeline, moment)
        self.show_current()

    def parse_datetime_input(self, text: str) -> datetime | None:
        text = " ".join(text.strip().split())
        match = DATE_TIME_RE.match(text)
        if match:
            year, month, day = (int(part) for part in match.group("date").split("-", 2))
            hour = int(match.group("hour"))
            minute = int(match.group("minute"))
            return datetime(year, month, day, hour, minute, tzinfo=KYIV_TZ)

        match = TIME_ONLY_RE.match(text)
        if match and self.timeline:
            hour = int(match.group("hour"))
            minute = int(match.group("minute"))
            reference = self.timeline[self.index].time.astimezone(KYIV_TZ)
            return reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return None

    def handle_text(self, text: str) -> None:
        text = text.strip()
        normalized = text.lower()

        if normalized in {"/start", "start", "help", "/help"}:
            self.send_help()
            self.show_current()
            return
        if normalized in {"n", "next", "/n", "/next"}:
            message = self.move(1)
            if message:
                self.bot.send_message(message)
            return
        if normalized in {"p", "prev", "/p", "/prev", "previous"}:
            message = self.move(-1)
            if message:
                self.bot.send_message(message)
            return
        if normalized in {"/events", "e", "/e", "events"}:
            self.show_current()
            return

        moment = self.parse_datetime_input(text)
        if moment is not None:
            self.goto_datetime(moment)
            return

        goto_match = GOTO_RE.match(text)
        if goto_match:
            message = self.goto_target(goto_match.group("target"))
            if message:
                self.bot.send_message(message)
            return

        self.bot.send_message(
            "Невідома команда. Надішліть /start для довідки.\n"
            "Для стрибка за часом: 2026-07-02 02:15"
        )

    def handle_rating_callback(
        self,
        data: str,
        *,
        bot_message_id: int,
        user_id: int | str,
        username: str | None,
    ) -> str | None:
        return apply_rating_callback(
            self.bot,
            chat_id=self.chat_id,
            data=data,
            bot_message_id=bot_message_id,
            user_id=user_id,
            username=username,
        )


class DebugBotRouter:
    def __init__(
        self,
        token: str,
        timeline: list[TimelineItem],
        posts_index: dict[str, dict[str, Any]],
    ) -> None:
        self.api_bot = TelegramBot(token)
        self.timeline = timeline
        self.posts_index = posts_index
        self.sessions: dict[str, DebugSession] = {}
        self.update_offset: int | None = None
        self._load_state()

    def _load_state(self) -> None:
        if not STATE_PATH.exists():
            return
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            self.update_offset = state.get("update_offset")
            chats = state.get("chats", {})
            for chat_id, chat_state in chats.items():
                self.sessions[chat_id] = DebugSession(
                    chat_id,
                    self.api_bot,
                    self.timeline,
                    self.posts_index,
                    index=int(chat_state.get("index", 0)),
                )
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Invalid debug state file, starting fresh")

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "update_offset": self.update_offset,
                    "chats": {
                        chat_id: {"index": session.index}
                        for chat_id, session in self.sessions.items()
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def session_for(self, chat_id: str) -> DebugSession:
        chat_id = str(chat_id)
        if chat_id not in self.sessions:
            self.sessions[chat_id] = DebugSession(
                chat_id,
                self.api_bot,
                self.timeline,
                self.posts_index,
            )
        return self.sessions[chat_id]

    def process_update(self, update: dict) -> None:
        update_id = int(update.get("update_id", 0))
        self.update_offset = update_id + 1

        callback = update.get("callback_query")
        if callback:
            self._process_callback(callback)
            self._save_state()
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return

        session = self.session_for(chat_id)
        text = message.get("text")
        if not text:
            session.bot.send_message("Підтримуються лише текстові команди.")
            self._save_state()
            return

        session.handle_text(text)
        self._save_state()

    def _process_callback(self, callback: dict[str, Any]) -> None:
        callback_id = str(callback.get("id", ""))
        data = str(callback.get("data") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return

        session = self.session_for(chat_id)
        try:
            message_id = message.get("message_id")
            from_user = callback.get("from") or {}
            if message_id is not None and str(data).startswith("rate:"):
                notice = session.handle_rating_callback(
                    data,
                    bot_message_id=int(message_id),
                    user_id=from_user.get("id", 0),
                    username=from_user.get("username"),
                )
            else:
                notice = "Невідома дія."
            if notice:
                self.api_bot.answer_callback_query(callback_id, text=notice)
            else:
                self.api_bot.answer_callback_query(callback_id)
        except Exception:
            logger.exception("Failed to handle callback %s", data)
            self.api_bot.answer_callback_query(callback_id, text="Помилка обробки.")

    def run(self) -> None:
        logger.info("Loaded %s timeline items", len(self.timeline))
        logger.info("Waiting for messages from any user...")

        while True:
            updates = self.api_bot.get_updates(offset=self.update_offset, timeout=30)
            for update in updates:
                try:
                    self.process_update(update)
                except Exception:
                    logger.exception("Failed to process update")


def main() -> None:
    jsonl_path = DEFAULT_JSONL_PATH
    events_path = DEFAULT_EVENTS_PATH

    posts = load_posts(jsonl_path)
    events = load_events(events_path)
    if not events:
        events, _, _ = __import__("news_events").group_events(posts)

    timeline = build_timeline(posts, events)
    posts_index = load_posts_index(jsonl_path)
    token = load_bot_token()
    DebugBotRouter(token, timeline, posts_index).run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
