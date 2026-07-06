from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from tg_data import BASE_DIR

KYIV_TZ = ZoneInfo("Europe/Kyiv")
RATINGS_PATH = BASE_DIR / "exports" / "ratings.jsonl"

RatingValue = Literal["bullshit", "valuable"]
ItemKind = Literal["event", "summary"]


@dataclass(frozen=True)
class RatingCallback:
    action: Literal["vote", "noop"]
    rating: RatingValue | None = None
    item_id: str | None = None


def item_kind_from_id(item_id: str) -> ItemKind:
    if item_id.startswith("evt_") or item_id.startswith("live_evt_"):
        return "event"
    return "summary"


def build_rating_keyboard(item_id: str, *, voted: RatingValue | None = None) -> dict[str, Any]:
    left_label = "🚫 bullshit" if voted == "bullshit" else "bullshit"
    right_label = "✅ valuable" if voted == "valuable" else "valuable"

    if voted:
        left_cb = right_cb = "rate:noop"
    else:
        left_cb = f"rate:bs:{item_id}"
        right_cb = f"rate:ok:{item_id}"

    return {
        "inline_keyboard": [
            [
                {"text": left_label, "callback_data": left_cb},
                {"text": right_label, "callback_data": right_cb},
            ]
        ]
    }


def parse_rating_callback(data: str) -> RatingCallback:
    if data == "rate:noop":
        return RatingCallback(action="noop")

    if data.startswith("rate:bs:"):
        return RatingCallback(action="vote", rating="bullshit", item_id=data[8:])

    if data.startswith("rate:ok:"):
        return RatingCallback(action="vote", rating="valuable", item_id=data[8:])

    return RatingCallback(action="noop")


def log_rating(
    *,
    user_id: int | str,
    username: str | None,
    chat_id: str,
    item_id: str,
    rating: RatingValue,
    bot_message_id: int,
    path: Path = RATINGS_PATH,
) -> None:
    record = {
        "ts": datetime.now(KYIV_TZ).isoformat(),
        "user_id": user_id,
        "username": username or "",
        "chat_id": chat_id,
        "item_id": item_id,
        "kind": item_kind_from_id(item_id),
        "rating": rating,
        "bot_message_id": bot_message_id,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
