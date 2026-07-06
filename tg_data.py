from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from news_events import EventGrouper, group_events

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JSONL_PATH = BASE_DIR / "exports" / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
DEFAULT_EVENTS_PATH = BASE_DIR / "exports" / "events.json"
KYIV_TZ = ZoneInfo("Europe/Kyiv")


def post_key(channel: object, message_id: object) -> str:
    return f"{channel}:{message_id}"


def parse_post_time(post: dict[str, Any]) -> datetime:
    raw = post.get("time") or post.get("date_kyiv") or post.get("date_utc") or ""
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return datetime.min.replace(tzinfo=KYIV_TZ)


def parse_event_time(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=KYIV_TZ)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=KYIV_TZ)


def load_posts(jsonl_path: Path = DEFAULT_JSONL_PATH) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON on line {line_number}: {exc}") from exc
    return posts


def load_posts_index(jsonl_path: Path = DEFAULT_JSONL_PATH) -> dict[str, dict[str, Any]]:
    return {
        post_key(post.get("channel"), post.get("message_id")): post
        for post in load_posts(jsonl_path)
    }


def load_events(path: Path = DEFAULT_EVENTS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def enrich_post(post: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    key = post_key(post.get("channel"), post.get("message_id"))
    source = index.get(key, {})
    merged = dict(post)
    merged["photo_path"] = source.get("photo_path")
    merged["has_media"] = source.get("has_media", False)
    if not merged.get("channel_url") and source.get("channel_url"):
        merged["channel_url"] = source.get("channel_url")
    return merged


def enrich_event_posts(
    event: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [enrich_post(post, index) for post in event.get("posts") or []]


def build_summary_set(posts: list[dict[str, Any]]) -> set[str]:
    grouper = EventGrouper()
    summary_posts: set[str] = set()
    for post in posts:
        text = str(post.get("text") or "").strip()
        if grouper.is_summary_post(text):
            summary_posts.add(post_key(post.get("channel"), post.get("message_id")))
    return summary_posts


def resolve_summary_posts(
    posts: list[dict[str, Any]],
    summary_keys: set[str] | None = None,
) -> set[str]:
    if summary_keys is not None:
        return summary_keys
    _, _, summary_posts = group_events(posts)
    return summary_posts


@dataclass(frozen=True)
class TimelineItem:
    kind: Literal["event", "summary"]
    time: datetime
    item_id: str
    event: dict[str, Any] | None = None
    summary_post: dict[str, Any] | None = None

    @property
    def end_time(self) -> datetime:
        if self.kind == "event" and self.event:
            return parse_event_time(self.event.get("last_post_at"))
        return self.time


def build_timeline(
    posts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    summary_keys: set[str] | None = None,
) -> list[TimelineItem]:
    summary_set = resolve_summary_posts(posts, summary_keys)
    items: list[TimelineItem] = []

    for event in events:
        items.append(
            TimelineItem(
                kind="event",
                time=parse_event_time(event.get("started_at")),
                item_id=str(event.get("id") or ""),
                event=event,
            )
        )

    for post in posts:
        key = post_key(post.get("channel"), post.get("message_id"))
        if key not in summary_set:
            continue
        items.append(
            TimelineItem(
                kind="summary",
                time=parse_post_time(post),
                item_id=key,
                summary_post=post,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            item.time,
            item.kind,
            item.item_id,
        ),
    )


def normalize_event_id(event_id: str) -> str:
    normalized = event_id.strip().lower()
    match = re.match(r"^evt_(\d+)$", normalized)
    if match:
        return f"evt_{int(match.group(1)):04d}"
    return normalized


def find_index_by_event_id(timeline: list[TimelineItem], event_id: str) -> int | None:
    normalized = normalize_event_id(event_id)
    for index, item in enumerate(timeline):
        if item.kind == "event" and item.item_id.lower() == normalized:
            return index
    return None


def find_index_by_item_id(timeline: list[TimelineItem], item_id: str) -> int | None:
    normalized = item_id.strip().lower()
    for index, item in enumerate(timeline):
        if item.item_id.lower() == normalized:
            return index
    return None


def find_nearest_index(timeline: list[TimelineItem], moment: datetime) -> int:
    if not timeline:
        return 0

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KYIV_TZ)

    inside = [
        index
        for index, item in enumerate(timeline)
        if item.time <= moment <= item.end_time
    ]
    if inside:
        return inside[0]

    return min(
        range(len(timeline)),
        key=lambda index: abs((timeline[index].time - moment).total_seconds()),
    )
