from __future__ import annotations

import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from news_events import EventGrouper, WEAPON_PRIORITY, load_aliases, normalize_for_search
from tg_data import TimelineItem, enrich_event_posts, parse_event_time, post_key

BASE_DIR = Path(__file__).resolve().parent
ALIASES_PATH = BASE_DIR / "event_aliases.json"

QUOTE_BLACKLIST_CHANNELS = frozenset(
    {
        "ukr_2025_ru",
        "ptahazzz",
        "rt_russian",
        "SolovievLive",
        "minomet120m",
    }
)

TARGET_PRIORITY = [
    "kyiv",
    "kharkiv",
    "odesa",
    "dnipro",
    "zaporizhzhia",
    "sumy",
    "poltava",
    "chernihiv",
]

PHASE_LABELS = {
    "launch": "Фаза: загроза пуску",
    "inbound": "Фаза: у напрямку цілі",
    "impact": "Фаза: приліт / ураження",
}

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]",
    flags=re.UNICODE,
)


@lru_cache(maxsize=1)
def load_labels() -> dict[str, str]:
    if ALIASES_PATH.exists():
        return load_aliases(ALIASES_PATH).get("labels", {})
    return {}


def escape_html(text: object) -> str:
    return escape(str(text or ""), quote=False)


def post_url(channel: object, message_id: object) -> str:
    return f"https://t.me/{channel}/{message_id}"


def post_link(post: dict[str, Any]) -> str:
    channel_url = str(post.get("channel_url") or "").strip().rstrip("/")
    message_id = post.get("message_id")
    if channel_url and message_id is not None:
        if "/c/" in channel_url:
            match = re.match(r"^(https://t\.me/c/)(?:-100)?(\d+)$", channel_url)
            if match:
                return f"{match.group(1)}{match.group(2)}/{message_id}"
        elif channel_url.startswith("https://t.me/"):
            return f"{channel_url}/{message_id}"
    channel = str(post.get("channel") or "").lstrip("@")
    return post_url(channel, message_id)


SUBSCRIBE_MARKERS = frozenset(
    {
        "подписаться",
        "подписатся",
        "підписатися",
        "подпишись",
        "труха",
        "надіслати",
        "макс",
    }
)


def strip_subscribe_footer(text: str) -> str:
    lines = text.splitlines()
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        normalized = normalize_for_search(last)
        if any(marker in normalized for marker in SUBSCRIBE_MARKERS):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def format_time_range(start_iso: str | None, end_iso: str | None) -> str:
    start = parse_event_time(start_iso)
    end = parse_event_time(end_iso)
    start_text = start.strftime("%H:%M")
    end_text = end.strftime("%H:%M")
    if start_text == end_text:
        return start_text
    return f"{start_text}–{end_text}"


def first_post_per_channel(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for post in posts:
        channel = str(post.get("channel") or "")
        if not channel or channel in seen:
            continue
        seen.add(channel)
        result.append(post)
    return result


def format_channel_link(post: dict[str, Any]) -> str:
    channel = str(post.get("channel") or "")
    return (
        f'<a href="{escape_html(post_link(post))}">'
        f"{escape_html(channel)}</a>"
    )


def format_channel_links(
    posts: list[dict[str, Any]],
    *,
    first_per_channel: bool = True,
) -> str:
    selected = first_post_per_channel(posts) if first_per_channel else posts
    return " · ".join(format_channel_link(post) for post in selected if post.get("channel"))


def label_value(labels: dict[str, str], item_id: str) -> str:
    return labels.get(item_id, item_id)


def pick_primary_weapon(weapons: list[str], labels: dict[str, str]) -> str | None:
    weapon_set = set(weapons)
    if not weapon_set:
        return None
    for weapon_id in WEAPON_PRIORITY:
        if weapon_id in weapon_set:
            return label_value(labels, weapon_id)
    return label_value(labels, sorted(weapon_set)[0])


def pick_target_labels(targets: list[str], labels: dict[str, str]) -> list[str]:
    if not targets:
        return []
    target_set = set(targets)
    ordered: list[str] = []
    for target_id in TARGET_PRIORITY:
        if target_id in target_set:
            ordered.append(label_value(labels, target_id))
    for target_id in sorted(target_set):
        label = label_value(labels, target_id)
        if label not in ordered:
            ordered.append(label)
    return ordered


def format_targets_for_headline(targets: list[str], labels: dict[str, str]) -> str:
    target_labels = pick_target_labels(targets, labels)
    if not target_labels:
        return ""
    if len(target_labels) <= 2:
        return ", ".join(target_labels)
    return f"{target_labels[0]}, {target_labels[1]} + ще {len(target_labels) - 2}"


def format_event_headline(event: dict[str, Any], labels: dict[str, str]) -> str:
    phase = event.get("phase")
    targets = event.get("targets") or []
    target_text = format_targets_for_headline(targets, labels)

    if phase == "all_clear":
        if target_text:
            return f"Відбій → {target_text}"
        return "Відбій"

    weapon_text = pick_primary_weapon(event.get("weapons") or [], labels) or "Загроза"
    count = event.get("count")
    count_prefix = f"{count} " if count else ""

    if target_text:
        return f"{count_prefix}{weapon_text} → {target_text}"
    return f"{count_prefix}{weapon_text}".strip()


def format_event_location(event: dict[str, Any], labels: dict[str, str]) -> str | None:
    targets = event.get("targets") or []
    if len(targets) <= 2 and "ukraine" not in targets:
        return None
    target_labels = pick_target_labels(targets, labels)
    if not target_labels:
        return None
    return f"Локація: {', '.join(target_labels)}"


def format_event_direction(event: dict[str, Any], labels: dict[str, str]) -> str | None:
    origins = event.get("origins") or []
    if not origins:
        return None
    origin_labels = [label_value(labels, origin_id) for origin_id in origins]
    if len(origin_labels) <= 3:
        joined = ", ".join(origin_labels)
    else:
        joined = f"{', '.join(origin_labels[:3])} + ще {len(origin_labels) - 3}"
    return f"Напрям: {joined}"


def format_event_phase(event: dict[str, Any]) -> str | None:
    phase = event.get("phase")
    if not phase or phase == "all_clear":
        return None
    return PHASE_LABELS.get(str(phase))


def strip_emojis(text: str) -> str:
    return EMOJI_RE.sub("", text).strip()


def pick_quote_text(
    event: dict[str, Any],
    posts_index: dict[str, dict[str, Any]],
    *,
    headline: str,
) -> str | None:
    grouper = EventGrouper()
    enriched_posts = enrich_event_posts(event, posts_index)
    best_post: dict[str, Any] | None = None
    best_score = -1

    for post in enriched_posts:
        channel = str(post.get("channel") or "")
        if channel in QUOTE_BLACKLIST_CHANNELS:
            continue
        text = str(post.get("text") or "").strip()
        if not text:
            continue
        fingerprint = grouper.fingerprint_post(text)
        score = grouper._score_post_for_message(post, fingerprint)
        if score > best_score:
            best_score = score
            best_post = post

    if not best_post or best_score < 4:
        return None

    text = str(best_post.get("text") or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    quote = strip_emojis(lines[0])
    if len(quote) > 120:
        quote = quote[:117].rstrip() + "..."
    if not quote:
        return None

    normalized_headline = normalize_for_search(headline)
    if normalize_for_search(quote) == normalized_headline:
        return None
    if quote.lower().startswith("http"):
        return None
    return quote


def unique_channel_count(posts: list[dict[str, Any]]) -> int:
    return len({str(post.get("channel") or "") for post in posts if post.get("channel")})


def format_event_text(
    event: dict[str, Any],
    posts_index: dict[str, dict[str, Any]],
    *,
    debug: bool = False,
    debug_meta: tuple[TimelineItem, int, int] | None = None,
) -> str:
    labels = load_labels()
    enriched_posts = enrich_event_posts(event, posts_index)
    headline = format_event_headline(event, labels)

    blocks: list[str] = [f"<b>{escape_html(headline)}</b>"]

    source_count = unique_channel_count(enriched_posts)
    time_text = format_time_range(event.get("started_at"), event.get("last_post_at"))
    blocks.append(escape_html(f"{time_text} · {source_count} джерел"))

    links = format_channel_links(enriched_posts, first_per_channel=True)
    if links:
        blocks.append(links)

    if debug and debug_meta is not None:
        blocks.append(escape_html(format_debug_footer(*debug_meta)))

    return "\n\n".join(blocks)


def format_summary_text(post: dict[str, Any]) -> str:
    text = strip_subscribe_footer(str(post.get("text") or "").strip())
    channel = str(post.get("channel") or "")
    blocks: list[str] = []
    if channel:
        blocks.append(format_channel_link(post))
    if text:
        blocks.append(escape_html(text))
    elif not blocks and post.get("message_id"):
        blocks.append(escape_html(post_link(post)))
    return "\n\n".join(blocks)


def format_photo_caption(photos: list[dict[str, Any]]) -> str:
    channels_with_photos = first_post_per_channel(photos)
    return format_channel_links(channels_with_photos, first_per_channel=False)


def format_debug_footer(item: TimelineItem, index: int, total: int) -> str:
    if item.kind == "event" and item.event:
        time_text = format_time_range(item.event.get("started_at"), item.event.get("last_post_at"))
        date_text = parse_event_time(item.event.get("started_at")).strftime("%Y-%m-%d")
        return f"[debug] {item.item_id} · {index + 1}/{total} · {date_text} {time_text}"
    date_text = item.time.strftime("%Y-%m-%d %H:%M")
    return f"[debug] summary {item.item_id} · {index + 1}/{total} · {date_text}"


def html_to_plain_preview(text: str) -> str:
    plain = re.sub(r"<a href=\"[^\"]+\">([^<]+)</a>", r"\1", text)
    plain = re.sub(r"</?b>", "", plain)
    plain = re.sub(r"</?i>", "", plain)
    return plain
