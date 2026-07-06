from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from news_events import EVENT_COLORS, THREAD_CLOSE_GRACE, THREAD_MIN_DURATION, EventGrouper, EventThread


class IngestKind(str, Enum):
    EMPTY = "empty"
    SUMMARY = "summary"
    STARTED = "started"
    MERGED = "merged"
    IGNORED = "ignored"


@dataclass(frozen=True)
class IngestResult:
    kind: IngestKind
    post_key: str | None = None
    thread_id: str | None = None


class LiveEventEngine:
    def __init__(self) -> None:
        self.grouper = EventGrouper()
        self.threads: list[EventThread] = []
        self._sent_ids: set[str] = set()
        self._next_id = 1

    def ingest(self, post: dict[str, Any]) -> IngestResult:
        text = str(post.get("text") or "").strip()
        if not text and not post.get("has_media"):
            return IngestResult(kind=IngestKind.EMPTY)

        key = self.grouper.post_key(post)
        if self.grouper.is_summary_post(text):
            return IngestResult(kind=IngestKind.SUMMARY, post_key=key)

        fp = self.grouper.fingerprint_post(text)
        post_time = self.grouper._post_time(post)

        matched_thread: EventThread | None = None
        for thread in reversed(self.threads):
            if thread.id in self._sent_ids:
                continue
            if self.grouper._can_merge(fp, thread, post_time):
                matched_thread = thread
                break

        started = False
        if matched_thread is None and self.grouper._can_start_thread(fp):
            matched_thread = EventThread(
                id=f"live_evt_{self._next_id:04d}",
                color_index=(self._next_id - 1) % len(EVENT_COLORS),
                started_at=post_time,
                last_post_at=post_time,
                close_at=post_time + THREAD_MIN_DURATION,
            )
            self._next_id += 1
            self.threads.append(matched_thread)
            started = True

        if matched_thread is None:
            return IngestResult(kind=IngestKind.IGNORED, post_key=key)

        self.grouper._merge_fingerprint(matched_thread, fp)
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
        matched_thread.user_message = self.grouper.build_user_message(matched_thread)

        kind = IngestKind.STARTED if started else IngestKind.MERGED
        return IngestResult(kind=kind, post_key=key, thread_id=matched_thread.id)

    def ready_threads(self, now: datetime) -> list[EventThread]:
        ready: list[EventThread] = []
        for thread in self.threads:
            if thread.id in self._sent_ids:
                continue
            if not thread.posts:
                continue
            if now > thread.close_at + THREAD_CLOSE_GRACE:
                ready.append(thread)
        return ready

    def mark_sent(self, thread_id: str) -> None:
        self._sent_ids.add(thread_id)

    def thread_to_event(self, thread: EventThread) -> dict[str, Any]:
        return self.grouper.thread_to_dict(thread)
