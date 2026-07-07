# tg-air-alerts

Single-file Telegram channel monitor for air alerts. All logic is in `monitor.py`.

## Setup

```bash
cp .env.example .env
# Fill in api_id, api_hash (my.telegram.org), TG_BOT_TOKEN (@BotFather), TELEGRAM_AUTHOR
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python monitor.py
```

First run prompts for phone + verification code interactively. Session files (`monitor_session.session`, `bot_session.session`) persist auth and are gitignored.

## Channel list

`tg-list-channels.csv` is tab-separated: `url\temoji`. The emoji identifies side (🇺🇦 Ukraine / 🐖 Russia). Only the Telegram username (after `t.me/`) is parsed.

## Architecture

- **User client** (`TelegramClient`) listens to `events.NewMessage` on resolved channels.
- **Bot client** (separate session) relays messages via `send_message` to `TELEGRAM_AUTHOR`.
- `process_message()` hook is a no-op stub — ready for OpenAI/Gemini analysis.
- Logging goes to both stdout and `monitor.log`.

## No tests, no lint, no typecheck

This project has none of those. Just `python monitor.py`.

## Conventions

- Code and docs are in **Ukrainian**.
- No formatter — match existing style (2 blank lines between top-level defs, spaces around operators).
