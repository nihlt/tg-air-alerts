"""Зупинити listener, прибрати lock. Опційно — відписатися від каналів."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import Channel

from tg_listener_process import find_python_listener_pids
from tg_telethon_io import EXPORTS_DIR, LEGACY_SQLITE_SESSION_PATH, create_telegram_client, load_channels

LOCK_FILE = EXPORTS_DIR / "listen_tg_channels.lock"


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_listener_processes() -> list[int]:
    stopped: list[int] = []
    for pid in find_python_listener_pids():
        if not _process_alive(pid):
            continue
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
        else:
            os.kill(pid, 15)
        stopped.append(pid)

    if stopped:
        time.sleep(2)

    return stopped


def clean_session_files() -> None:
    LOCK_FILE.unlink(missing_ok=True)
    for suffix in ("-journal", "-wal", "-shm"):
        path = LEGACY_SQLITE_SESSION_PATH.with_suffix(f".session{suffix}")
        try:
            path.unlink(missing_ok=True)
        except OSError:
            print(f"   [warn] could not remove {path.name}")


async def leave_all_channels() -> int:
    client = await create_telegram_client()
    left = 0
    try:
        for url in load_channels():
            try:
                entity = await client.get_entity(url)
            except Exception as exc:
                print(f"[skip] {url}: {exc}")
                continue
            if not isinstance(entity, Channel):
                print(f"[skip] {url}: not a channel")
                continue
            try:
                await client(LeaveChannelRequest(entity))
                left += 1
                print(f"[left] {url}")
            except UserNotParticipantError:
                print(f"[ok] not subscribed: {url}")
            except Exception as exc:
                print(f"[warn] {url}: {exc}")
    finally:
        if client.is_connected():
            await client.disconnect()
    return left


def main() -> None:
    parser = argparse.ArgumentParser(description="Stop listener and clean lock files.")
    parser.add_argument(
        "--leave",
        action="store_true",
        help="Also unsubscribe from all channels in tg-chanel-links.csv",
    )
    args = parser.parse_args()

    print("=== cleanup listener ===\n")

    print("1) Stop listener processes")
    stopped = stop_listener_processes()
    if stopped:
        print(f"   stopped pid: {', '.join(map(str, stopped))}")
    else:
        print("   no active listener")

    print("\n2) Clean lock / session files")
    clean_session_files()
    print("   done")

    if args.leave:
        print("\n3) Leave channels from tg-chanel-links.csv")
        try:
            left = asyncio.run(leave_all_channels())
        except RuntimeError as exc:
            print(f"   error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"\nDone. Left {left} channel(s).")
    else:
        print("\n3) Channel subscriptions kept (use --leave to unsubscribe)")
        print("\nDone.")


if __name__ == "__main__":
    main()
