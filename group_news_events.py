import json
from pathlib import Path

from news_events import group_events

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "exports" / "tg_posts_2026-07-01_1600_to_2026-07-02_0800.jsonl"
OUTPUT_PATH = BASE_DIR / "exports" / "events.json"
REPORT_PATH = BASE_DIR / "exports" / "events_report.txt"

TSIRKON_POST_KEYS = {
    "eRadarrua:99144",
    "truexakyiv:79249",
    "monitoring_zaxid:22942",
    "eRadarrua:99145",
    "truexanewsua:140236",
}
EXCLUDED_POST_KEYS = {
    "kyivske_nebo:56384",
    "ukr_2025_ru:320096",
}


def load_posts() -> list[dict]:
    posts = []
    with INPUT_PATH.open("r", encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                posts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON on line {line_number}: {exc}") from exc
    return posts


def post_key(post: dict) -> str:
    return f"{post.get('channel')}:{post.get('message_id')}"


def build_report(
    events: list[dict],
    assignment: dict[str, str],
    summary_posts: set[str],
    total_posts: int,
) -> str:
    grouped_posts = len(assignment)
    lines = [
        "Events grouping report",
        f"Input posts: {total_posts}",
        f"Detected events: {len(events)}",
        f"Grouped posts: {grouped_posts}",
        f"Summary posts (3+ location tags): {len(summary_posts)}",
        "",
        "Top 15 events by source count:",
    ]

    for event in sorted(events, key=lambda item: item["source_count"], reverse=True)[:15]:
        lines.append(
            f"  {event['source_count']:3d} sources  {event['id']}  "
            f"{event['started_at'][:19]} – {event['last_post_at'][19:]}  "
            f"{event['user_message'][:80]}"
        )

    tsirkon_event_ids = {
        assignment[key]
        for key in TSIRKON_POST_KEYS
        if key in assignment
    }
    lines.extend(["", "Tsirkon benchmark cluster:"])
    if len(tsirkon_event_ids) == 1:
        event_id = next(iter(tsirkon_event_ids))
        event = next(item for item in events if item["id"] == event_id)
        lines.append(f"  OK: all benchmark posts in {event_id}")
        lines.append(f"  Message: {event['user_message']}")
        lines.append(f"  Sources: {event['source_count']}")
        lines.append(f"  Send at: {event['send_at']}")
    else:
        lines.append(f"  NEEDS TUNING: benchmark posts span {sorted(tsirkon_event_ids) or ['ungrouped']}")

    lines.extend(["", "Excluded benchmark posts:"])
    for key in sorted(EXCLUDED_POST_KEYS):
        event_id = assignment.get(key)
        lines.append(f"  {key}: {event_id or 'ungrouped'}")

    multi_source = sum(1 for event in events if event["source_count"] > 1)
    lines.extend(
        [
            "",
            f"Events with 2+ sources: {multi_source}",
            f"Events with 1 source: {len(events) - multi_source}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    posts = load_posts()
    events, assignment, summary_posts = group_events(posts)

    OUTPUT_PATH.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    REPORT_PATH.write_text(
        build_report(events, assignment, summary_posts, len(posts)),
        encoding="utf-8",
        newline="\n",
    )

    print(f"Wrote {len(events)} events to {OUTPUT_PATH}")
    print(f"Summary posts: {len(summary_posts)}")
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
