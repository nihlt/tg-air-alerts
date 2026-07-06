from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tg_data import (
    DEFAULT_EVENTS_PATH,
    DEFAULT_JSONL_PATH,
    build_timeline,
    enrich_event_posts,
    enrich_post,
    load_events,
    load_posts,
    load_posts_index,
)
from tg_format import format_event_text, format_summary_text, html_to_plain_preview
from tg_send import collect_photos, load_bot_config, send_event_alert, send_summary_alert, TelegramBot


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def print_text(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or send Telegram alerts.")
    parser.add_argument("--event", help="Event id, e.g. evt_0004")
    parser.add_argument("--summary", help="Summary post key, e.g. eRadarrua:98922")
    parser.add_argument("--send", action="store_true", help="Send to Telegram instead of preview")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL_PATH)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--timeline", action="store_true", help="Print timeline summary")
    return parser


def print_timeline_summary(jsonl_path: Path, events_path: Path) -> None:
    posts = load_posts(jsonl_path)
    events = load_events(events_path)
    timeline = build_timeline(posts, events)
    print_text(f"Timeline items: {len(timeline)}")
    for item in timeline[:5]:
        print_text(f"  {item.kind:7} {item.item_id} {item.time.isoformat()}")


def preview_event(event_id: str, jsonl_path: Path, events_path: Path) -> None:
    posts_index = load_posts_index(jsonl_path)
    events = load_events(events_path)
    event = next((item for item in events if item.get("id") == event_id), None)
    if event is None:
        raise SystemExit(f"Event not found: {event_id}")

    text = format_event_text(event, posts_index)
    print_text("=== EVENT TEXT ===")
    print_text(html_to_plain_preview(text))
    print_text("")
    print_text("=== HTML ===")
    print_text(text)
    print_text("")
    photos = collect_photos(enrich_event_posts(event, posts_index))
    print_text(f"Photos: {len(photos)}")
    for photo in photos:
        print_text(f"  {photo['path']}")


def preview_summary(summary_key: str, jsonl_path: Path) -> None:
    posts_index = load_posts_index(jsonl_path)
    post = posts_index.get(summary_key)
    if post is None:
        raise SystemExit(f"Summary post not found: {summary_key}")
    enriched = enrich_post(post, posts_index)
    text = format_summary_text(enriched)
    print_text("=== SUMMARY TEXT ===")
    print_text(html_to_plain_preview(text))
    print_text("")
    print_text("=== HTML ===")
    print_text(text)
    print_text("")
    photos = collect_photos([enriched])
    print_text(f"Photos: {len(photos)}")
    for photo in photos:
        print_text(f"  {photo['path']}")


def main() -> None:
    configure_stdout()
    parser = build_parser()
    args = parser.parse_args()

    if args.timeline:
        print_timeline_summary(args.jsonl, args.events)
        return

    if not args.event and not args.summary:
        parser.error("Specify --event, --summary, or --timeline")

    if args.event:
        if args.send:
            token, chat_id = load_bot_config()
            bot = TelegramBot(token, chat_id)
            posts_index = load_posts_index(args.jsonl)
            event = next(
                (item for item in load_events(args.events) if item.get("id") == args.event),
                None,
            )
            if event is None:
                raise SystemExit(f"Event not found: {args.event}")
            send_event_alert(bot, event, posts_index)
            print_text(f"Sent event {args.event}")
        else:
            preview_event(args.event, args.jsonl, args.events)
        return

    if args.summary:
        if args.send:
            token, chat_id = load_bot_config()
            bot = TelegramBot(token, chat_id)
            posts_index = load_posts_index(args.jsonl)
            post = posts_index.get(args.summary)
            if post is None:
                raise SystemExit(f"Summary post not found: {args.summary}")
            send_summary_alert(bot, post, posts_index)
            print_text(f"Sent summary {args.summary}")
        else:
            preview_summary(args.summary, args.jsonl)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
