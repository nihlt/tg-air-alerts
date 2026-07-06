"""One-time: export telegram_export.session (SQLite) -> telegram_session.txt (plain text)."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import SQLiteSession

from tg_listener_process import find_python_listener_pids, stop_listeners
from tg_telethon_io import (
    LEGACY_SQLITE_SESSION_PATH,
    SESSION_STRING_PATH,
    load_config,
    load_session_string,
    prompt_for_phone,
    save_session_string,
)


async def migrate() -> None:
    if load_session_string():
        print(f"Already exists: {SESSION_STRING_PATH.name}")
        return

    source = LEGACY_SQLITE_SESSION_PATH.with_suffix(".session")
    if not source.exists():
        raise RuntimeError("No telegram_export.session found to migrate.")

    api_id, api_hash, phone, bot_token = load_config()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "migrate_copy"
        shutil.copy2(source, base.with_suffix(".session"))
        for suffix in ("-journal", "-wal", "-shm"):
            extra = source.with_suffix(f".session{suffix}")
            if extra.exists():
                shutil.copy2(extra, base.with_suffix(f".session{suffix}"))

        legacy = SQLiteSession(str(base))
        client = TelegramClient(legacy, api_id, api_hash)
        try:
            if bot_token:
                await client.start(bot_token=bot_token)
            else:
                await client.start(phone=prompt_for_phone(phone))
            save_session_string(client)
            print(f"Saved {SESSION_STRING_PATH.name}")
            print("Old telegram_export.session* can be deleted manually.")
        finally:
            if client.is_connected():
                await client.disconnect()


def main() -> None:
    print("Stopping listeners...")
    for pid in find_python_listener_pids():
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
        else:
            import os
            os.kill(pid, 15)
        print(f"Stopped pid {pid}")

    asyncio.run(migrate())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
