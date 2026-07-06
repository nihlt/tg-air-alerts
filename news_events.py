from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
MARKERS_PATH = BASE_DIR / "tg-news-markers.json"
ALIASES_PATH = BASE_DIR / "event_aliases.json"

THREAD_MIN_DURATION = timedelta(minutes=2)
THREAD_TAIL_SILENCE = timedelta(seconds=15)
THREAD_CLOSE_GRACE = timedelta(seconds=60)
WEAPONLESS_MERGE_WINDOW = timedelta(seconds=20)
SUMMARY_LOCATION_TAG_LIMIT = 2

EVENT_COLORS = [
    "#ef4444",
    "#f97316",
    "#eab308",
    "#84cc16",
    "#22c55e",
    "#14b8a6",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#ec4899",
    "#f43f5e",
    "#0ea5e9",
]

PHASE_ORDER = {"launch": 0, "inbound": 1, "impact": 2, "all_clear": 3}
GENERIC_WEAPONS = {"rocket", "ballistic"}

WEAPON_PRIORITY = [
    "tsirkon",
    "kinzhal",
    "iskander",
    "kalibr",
    "cruise",
    "shahed",
    "grad",
    "point_u",
    "s300",
    "fpv",
    "kab",
    "ballistic",
    "rocket",
]


def normalize_for_search(value: str) -> str:
    return value.casefold().replace("ё", "е").replace("Ё", "е")


WORD_CHAR_CLASS = r"a-z0-9а-яіїєґё"
WORD_START = rf"(?<![{WORD_CHAR_CLASS}])"
WORD_END = rf"(?![{WORD_CHAR_CLASS}])"

# Categories where a match may continue into suffix letters (київ → київщині, циркон → циркони).
PREFIX_MATCH_CATEGORIES = frozenset({"location", "target", "origin", "phase", "other", "default"})


@functools.lru_cache(maxsize=4096)
def _compile_pattern_regex(pattern: str, category: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    if category in {"weapon", "equipment"}:
        if len(pattern) < 4:
            body = rf"{WORD_START}{escaped}{WORD_END}"
        else:
            body = rf"{WORD_START}{escaped}"
    elif category in PREFIX_MATCH_CATEGORIES:
        body = rf"{WORD_START}{escaped}"
    else:
        if len(pattern) < 4:
            body = rf"{WORD_START}{escaped}{WORD_END}"
        else:
            body = rf"{WORD_START}{escaped}"
    return re.compile(body, re.IGNORECASE)


def pattern_matches_normalized(
    normalized: str,
    pattern: str,
    *,
    category: str = "default",
    canonical_id: str | None = None,
) -> bool:
    del canonical_id
    if not pattern:
        return False
    return bool(_compile_pattern_regex(pattern, category).search(normalized))


def load_markers(path: Path = MARKERS_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_alias_index(groups: dict[str, list[str]]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for canonical_id, patterns in groups.items():
        for pattern in patterns:
            entries.append((normalize_for_search(pattern), canonical_id))
    entries.sort(key=lambda item: len(item[0]), reverse=True)
    return entries


@dataclass
class PostFingerprint:
    weapons: set[str] = field(default_factory=set)
    targets: set[str] = field(default_factory=set)
    origins: set[str] = field(default_factory=set)
    count: int | None = None
    phase: str | None = None

    def has_signal(self) -> bool:
        return bool(self.weapons or self.targets or self.origins)


@dataclass
class EventThread:
    id: str
    color_index: int
    started_at: datetime
    last_post_at: datetime
    close_at: datetime
    weapons: set[str] = field(default_factory=set)
    targets: set[str] = field(default_factory=set)
    origins: set[str] = field(default_factory=set)
    count: int | None = None
    phase: str | None = None
    posts: list[dict[str, Any]] = field(default_factory=list)
    user_message: str = ""
    send_at: datetime | None = None

    def is_open_at(self, moment: datetime, grace: timedelta = THREAD_CLOSE_GRACE) -> bool:
        return moment <= self.close_at + grace

    def refresh_close_at(self) -> None:
        self.close_at = max(
            self.started_at + THREAD_MIN_DURATION,
            self.last_post_at + THREAD_TAIL_SILENCE,
        )
        self.send_at = self.close_at


class EventGrouper:
    def __init__(self, markers: list[dict[str, str]] | None = None, aliases: dict[str, Any] | None = None) -> None:
        self.aliases = aliases or load_aliases()
        self.labels: dict[str, str] = self.aliases.get("labels", {})
        self.target_index = _build_alias_index(self.aliases.get("targets", {}))
        self.weapon_index = _build_alias_index(self.aliases.get("weapons", {}))
        self.origin_index = _build_alias_index(self.aliases.get("origins", {}))
        self.phase_index = _build_alias_index(self.aliases.get("phase_markers", {}))
        self.count_pattern = re.compile(
            rf"(\d+)\s*(?:х|x|шт\.?)?\s*(?:{self.aliases.get('weapon_count_words', 'бпла')})",
            re.IGNORECASE,
        )
        self._markers_by_category = self._group_markers(markers or load_markers())

    def _group_markers(self, markers: list[dict[str, str]]) -> dict[str, list[tuple[str, str]]]:
        grouped: dict[str, list[tuple[str, str]]] = {
            "location": [],
            "weapon": [],
            "equipment": [],
            "other": [],
        }
        for marker in markers:
            category = marker.get("category", "other")
            text = marker.get("text", "")
            if category in grouped and text:
                grouped[category].append((normalize_for_search(text), text))
        for category in grouped:
            grouped[category].sort(key=lambda item: len(item[0]), reverse=True)
        return grouped

    def _match_index(self, text: str, index: list[tuple[str, str]], *, category: str = "default") -> set[str]:
        normalized = normalize_for_search(text)
        found: set[str] = set()
        for pattern, canonical_id in index:
            if pattern_matches_normalized(normalized, pattern, category=category, canonical_id=canonical_id):
                found.add(canonical_id)
        return found

    def _detect_phase(self, text: str) -> str | None:
        normalized = normalize_for_search(text)
        for phase, patterns in self.aliases.get("phase_markers", {}).items():
            for pattern in patterns:
                if pattern_matches_normalized(
                    normalized,
                    normalize_for_search(pattern),
                    category="phase",
                ):
                    return phase
        return None

    def _extract_count(self, text: str) -> int | None:
        match = self.count_pattern.search(text)
        if not match:
            return None
        return int(match.group(1))

    def _markers_in_text(self, text: str, category: str) -> set[str]:
        normalized = normalize_for_search(text)
        found: set[str] = set()
        for pattern, original in self._markers_by_category.get(category, []):
            if pattern_matches_normalized(normalized, pattern, category=category):
                found.add(original)
        return found

    def location_tags_in_text(self, text: str) -> set[str]:
        return self._markers_in_text(text, "location")

    def is_summary_post(self, text: str) -> bool:
        return len(self.location_tags_in_text(text)) > SUMMARY_LOCATION_TAG_LIMIT

    def fingerprint_post(self, text: str) -> PostFingerprint:
        text = text or ""
        fp = PostFingerprint()
        fp.weapons = self._match_index(text, self.weapon_index, category="weapon")
        fp.targets = self._match_index(text, self.target_index, category="target")
        fp.origins = self._match_index(text, self.origin_index, category="origin")

        marker_weapons = self._markers_in_text(text, "weapon")
        for marker in marker_weapons:
            fp.weapons |= self._match_index(marker, self.weapon_index, category="weapon")

        marker_locations = self._markers_in_text(text, "location")
        for marker in marker_locations:
            fp.targets |= self._match_index(marker, self.target_index)

        fp.count = self._extract_count(text)
        fp.phase = self._detect_phase(text)
        return fp

    def _targets_compatible(self, left: set[str], right: set[str]) -> bool:
        if not left or not right:
            return True
        if left & right:
            return True
        kyiv_family = {"kyiv", "kyiv_region", "brovary", "boryspil"}
        if left <= kyiv_family and right <= kyiv_family:
            return True
        return False

    def _phases_compatible(self, post_phase: str | None, thread_phase: str | None) -> bool:
        if not post_phase or not thread_phase:
            return True
        if post_phase == "all_clear":
            return thread_phase != "all_clear"
        if thread_phase == "all_clear":
            return False
        return True

    def _weapons_compatible(self, post_weapons: set[str], thread_weapons: set[str]) -> bool:
        if not post_weapons or not thread_weapons:
            return True
        if post_weapons & thread_weapons:
            return True
        post_specific = post_weapons - GENERIC_WEAPONS
        thread_specific = thread_weapons - GENERIC_WEAPONS
        if not post_specific or not thread_specific:
            return True
        return False

    def _can_merge(self, fp: PostFingerprint, thread: EventThread, post_time: datetime) -> bool:
        if not thread.is_open_at(post_time):
            return False
        if not self._phases_compatible(fp.phase, thread.phase):
            return False
        if not self._targets_compatible(fp.targets, thread.targets):
            return False

        if fp.weapons and thread.weapons:
            return self._weapons_compatible(fp.weapons, thread.weapons)

        if fp.weapons and not thread.weapons:
            return True

        if not fp.weapons and thread.weapons:
            if post_time - thread.last_post_at > WEAPONLESS_MERGE_WINDOW:
                return False
            if fp.targets and thread.targets and (fp.targets & thread.targets):
                return fp.phase in {None, "inbound", "impact", "launch"}
            if fp.origins and thread.origins and (fp.origins & thread.origins):
                return fp.phase in {None, "launch"}
        return False

    def _can_start_thread(self, fp: PostFingerprint) -> bool:
        if fp.weapons:
            return True
        if fp.weapons and fp.origins:
            return True
        return False

    def _merge_fingerprint(self, thread: EventThread, fp: PostFingerprint) -> None:
        thread.weapons |= fp.weapons
        thread.targets |= fp.targets
        thread.origins |= fp.origins
        if fp.count is not None:
            if thread.count is None or fp.count > thread.count:
                thread.count = fp.count
        if fp.phase:
            if thread.phase is None:
                thread.phase = fp.phase
            elif PHASE_ORDER.get(fp.phase, 0) > PHASE_ORDER.get(thread.phase, 0):
                thread.phase = fp.phase

    def _label_weapon(self, weapon_id: str) -> str:
        return self.labels.get(weapon_id, weapon_id)

    def _label_target(self, target_id: str) -> str:
        return self.labels.get(target_id, target_id)

    def _pick_primary_weapon(self, weapons: set[str]) -> str | None:
        if not weapons:
            return None
        for weapon_id in WEAPON_PRIORITY:
            if weapon_id in weapons:
                return weapon_id
        return sorted(weapons)[0]

    def _pick_primary_target(self, targets: set[str]) -> str | None:
        if not targets:
            return None
        priority = ["kyiv", "kharkiv", "odesa", "dnipro", "zaporizhzhia", "sumy", "poltava", "chernihiv"]
        for item in priority:
            if item in targets:
                return item
        return sorted(targets)[0]

    def _score_post_for_message(self, post: dict[str, Any], fp: PostFingerprint) -> int:
        text = str(post.get("text") or "").strip()
        score = 0
        if fp.count is not None:
            score += 3
        if fp.targets:
            score += 2
        if fp.weapons:
            score += 2
        if 10 <= len(text) <= 180:
            score += 1
        if "надіслати" in normalize_for_search(text) or "підписатися" in normalize_for_search(text):
            score -= 2
        return score

    def build_user_message(self, thread: EventThread) -> str:
        best_post: dict[str, Any] | None = None
        best_score = -1
        for post in thread.posts:
            fp = self.fingerprint_post(str(post.get("text") or ""))
            score = self._score_post_for_message(post, fp)
            if score > best_score:
                best_score = score
                best_post = post

        weapon_id = self._pick_primary_weapon(thread.weapons)
        target_id = self._pick_primary_target(thread.targets)
        weapon_label = self._label_weapon(weapon_id) if weapon_id else "Загроза"
        target_label = self._label_target(target_id) if target_id else None

        if best_post and best_score >= 4:
            text = str(best_post.get("text") or "").strip()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                first_line = lines[0]
                if len(first_line) <= 120 and not first_line.lower().startswith("http"):
                    if thread.count and str(thread.count) not in first_line:
                        pass
                    else:
                        return first_line

        if thread.count and weapon_label and target_label:
            return f"{thread.count} {weapon_label} → {target_label}"
        if weapon_label and target_label:
            return f"{weapon_label} → {target_label}"
        if weapon_label:
            return weapon_label
        if target_label:
            return f"Подія: {target_label}"
        if best_post:
            return str(best_post.get("text") or "").strip()[:120]
        return "Подія"

    def _post_time(self, post: dict[str, Any]) -> datetime:
        raw = post.get("date_kyiv") or post.get("date_utc") or ""
        try:
            return datetime.fromisoformat(str(raw))
        except ValueError:
            return datetime.min

    def post_key(self, post: dict[str, Any]) -> str:
        return f"{post.get('channel')}:{post.get('message_id')}"

    def group_posts(
        self, posts: list[dict[str, Any]]
    ) -> tuple[list[EventThread], dict[str, str], set[str]]:
        sorted_posts = sorted(
            posts,
            key=lambda post: (
                self._post_time(post),
                str(post.get("channel") or ""),
                int(post.get("message_id") or 0),
            ),
        )

        threads: list[EventThread] = []
        assignment: dict[str, str] = {}
        summary_posts: set[str] = set()
        next_id = 1

        for post in sorted_posts:
            text = str(post.get("text") or "").strip()
            if not text and not post.get("has_media"):
                continue

            if self.is_summary_post(text):
                summary_posts.add(self.post_key(post))
                continue

            fp = self.fingerprint_post(text)
            post_time = self._post_time(post)

            matched_thread: EventThread | None = None
            for thread in reversed(threads):
                if self._can_merge(fp, thread, post_time):
                    matched_thread = thread
                    break

            if matched_thread is None and self._can_start_thread(fp):
                matched_thread = EventThread(
                    id=f"evt_{next_id:04d}",
                    color_index=(next_id - 1) % len(EVENT_COLORS),
                    started_at=post_time,
                    last_post_at=post_time,
                    close_at=post_time + THREAD_MIN_DURATION,
                )
                next_id += 1
                threads.append(matched_thread)

            if matched_thread is None:
                continue

            self._merge_fingerprint(matched_thread, fp)
            matched_thread.last_post_at = post_time
            matched_thread.posts.append(
                {
                    "channel": post.get("channel"),
                    "channel_url": post.get("channel_url"),
                    "message_id": post.get("message_id"),
                    "time": post_time.isoformat(),
                    "text": text,
                }
            )
            matched_thread.refresh_close_at()
            matched_thread.user_message = self.build_user_message(matched_thread)
            assignment[self.post_key(post)] = matched_thread.id

        finalized = [thread for thread in threads if len(thread.posts) >= 1]
        return finalized, assignment, summary_posts

    def thread_to_dict(self, thread: EventThread) -> dict[str, Any]:
        channels = sorted({str(post.get("channel") or "") for post in thread.posts if post.get("channel")})
        return {
            "id": thread.id,
            "color_index": thread.color_index,
            "color": EVENT_COLORS[thread.color_index % len(EVENT_COLORS)],
            "started_at": thread.started_at.isoformat(),
            "last_post_at": thread.last_post_at.isoformat(),
            "close_at": thread.close_at.isoformat(),
            "send_at": (thread.send_at or thread.close_at).isoformat(),
            "weapons": sorted(thread.weapons),
            "targets": sorted(thread.targets),
            "origins": sorted(thread.origins),
            "count": thread.count,
            "phase": thread.phase,
            "user_message": thread.user_message,
            "source_count": len(thread.posts),
            "channels": channels,
            "posts": thread.posts,
        }


def group_events(
    posts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], set[str]]:
    grouper = EventGrouper()
    threads, assignment, summary_posts = grouper.group_posts(posts)
    return [grouper.thread_to_dict(thread) for thread in threads], assignment, summary_posts


def event_color(color_index: int) -> str:
    return EVENT_COLORS[color_index % len(EVENT_COLORS)]
