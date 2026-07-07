# TG Air Alerts — Agent Guide

## Repo at a glance

Two parallel pipelines sharing the same grouping engine (`news_events.py`):

- **Batch export**: `download_tg_posts.py` → `build_news_html.py` / `build_news_markers.py`
- **Live listener**: `listen_tg_channels.py` + bot (`tg_send.py`, `tg_bot_handlers.py`)

Both write to `exports/` (fully gitignored). All paths derive from `Path(__file__).resolve().parent` — no configurable base dir.

## Developer commands

```bash
python download_tg_posts.py          # batch export (hardcoded time window — edit file)
python build_news_html.py             # generate exports/news.html
python build_news_markers.py          # autogen tg-news-markers.json (run before rebuild-html)
python group_news_events.py           # standalone event grouping → exports/events.json
python listen_tg_channels.py [--leave-on-exit]  # live daemon
python preview_tg_alert.py --event evt_0001 [--send]  # preview/send alert
python cleanup_listener.py [--leave]  # kill listener (stop_listener.py is an alias)
python migrate_telegram_session.py    # SQLite → StringSession migration
sh run_listener.sh                    # cleanup + start listener
```

No test framework, no pytest, no test files.

## CLI conventions

Only listener-adjacent scripts use `argparse`. The export pipeline scripts (`download_tg_posts.py`, `build_news_html.py`, `build_news_markers.py`, `group_news_events.py`) have **hardcoded paths and constants** — edit the source file to change inputs/outputs or the time window (`START_KYIV` / `END_KYIV` in `download_tg_posts.py`).

## Quirks & gotchas

- **No `python-telegram-bot`**. Bot API client (`tg_send.py`) is hand-rolled via `urllib.request` with manual multipart — intentional to avoid asyncio conflicts with Telethon.
- **StringSession, not SQLite**. The `telegram_session.txt` file is plain-text Telethon session (migrated away from SQLite to dodge `database is locked` concurrency errors).
- **Two `.env` key domains** read by separate `dotenv_values()` calls — `tg_telethon_io.py` needs `api_id`/`api_hash`/`phone`/`bot_token`; `tg_send.py` needs `TG_BOT_TOKEN`/`TELEGRAM_AUTHOR`.
- **`telegram_session.txt` is read AND written** on every client startup (`save_session_string()`).
- **Stance emoji filtering**: `tg-chanel-links.csv` has a `stance` column with 🇺🇦 (pro-Ukraine) or 🐖 (pro-Russia) — used in the HTML UI filter.
- **No migration / alembic / schema versioning**. The live listener state (`exports/live_listener_state.json`), subscriber file (`tg_subscribers.json`), and debug state (`exports/debug_state.json`) are plain JSON with no migration path.
- **Ad detection** in `tg_telethon_io.is_ad_message()` uses a weighted scoring heuristic (invite links + CTA phrases + external mentions ≥ 3 points).
- **`event_aliases.json`** drives the grouping engine — weapon/target/origin name normalization. Modify this file to change how posts cluster, not the code.

## Generated artifacts (all gitignored under `exports/`)

| File | From | Notes |
|------|------|-------|
| `exports/tg_posts_*.jsonl` | `download_tg_posts.py` | Newline-delimited JSON, one post per line |
| `exports/tg_posts_live.jsonl` | `listen_tg_channels.py` | Same schema, live feed |
| `exports/news.html` | `build_news_html.py` | Self-contained (JS + CSS inline) |
| `exports/events.json` | `group_news_events.py` | Output of event grouping |
| `exports/events_report.txt` | `group_news_events.py` | Validation report for tuning |
| `exports/markers_report.txt` | `build_news_markers.py` | Marker quality report |
| `exports/ratings.jsonl` | bot (via `tg_rating.py`) | User rating votes |
| `exports/live_listener_state.json` | `listen_tg_channels.py` | Bot update_offset persistence |
| `exports/debug_state.json` | `tg_bot_debug.py` | Per-chat debug navigator state |
| `exports/photos/` | Both pipelines | Organized by `channel_name/` |
