from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tg_telethon_io import EXPORTS_DIR, LEGACY_SQLITE_SESSION_PATH, ensure_export_dirs

LISTENER_LOCK_PATH = EXPORTS_DIR / "listen_tg_channels.lock"
LISTENER_SCRIPT_NAME = "listen_tg_channels.py"


def find_python_listener_pids(listener_script: str = LISTENER_SCRIPT_NAME, *, exclude_pid: int | None = None) -> list[int]:
    exclude_pid = exclude_pid if exclude_pid is not None else os.getpid()
    pids: set[int] = set()

    if sys.platform == "win32":
        command = (
            "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | "
            f"Where-Object {{ $_.CommandLine -match '{listener_script}' }} | "
            "ForEach-Object { $_.ProcessId }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
    else:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            if listener_script not in line:
                continue
            pid_text = line.strip().split(None, 1)[0]
            if pid_text.isdigit():
                pids.add(int(pid_text))

    return sorted(pid for pid in pids if pid != exclude_pid)


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock_pid() -> int | None:
    if not LISTENER_LOCK_PATH.exists():
        return None
    try:
        return int(LISTENER_LOCK_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def find_listener_pids(*, exclude_pid: int | None = None) -> list[int]:
    exclude_pid = exclude_pid if exclude_pid is not None else os.getpid()
    pids: set[int] = set()

    lock_pid = _read_lock_pid()
    if lock_pid is not None:
        pids.add(lock_pid)

    pids.update(find_python_listener_pids("listen_tg_channels.py", exclude_pid=exclude_pid))
    pids.update(find_python_listener_pids("tg_bot_debug.py", exclude_pid=exclude_pid))
    return sorted(pids)


def cleanup_listener_artifacts() -> None:
    LISTENER_LOCK_PATH.unlink(missing_ok=True)


def stop_listeners(*, wait_seconds: float = 2.0) -> list[int]:
    ensure_export_dirs()
    stopped: list[int] = []

    for pid in find_listener_pids():
        if not process_exists(pid):
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
        stopped.append(pid)

    if stopped and wait_seconds > 0:
        time.sleep(wait_seconds)

    cleanup_listener_artifacts()
    return stopped


def acquire_listener_lock() -> None:
    ensure_export_dirs()
    lock_pid = _read_lock_pid()
    if lock_pid is not None and process_exists(lock_pid) and lock_pid != os.getpid():
        raise RuntimeError(
            f"Another listener is already running (pid {lock_pid}). "
            "Run cleanup_listener.sh first."
        )
    if LISTENER_LOCK_PATH.exists():
        LISTENER_LOCK_PATH.unlink(missing_ok=True)
    LISTENER_LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")


def release_listener_lock() -> None:
    try:
        lock_pid = _read_lock_pid()
        if lock_pid == os.getpid():
            LISTENER_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        LISTENER_LOCK_PATH.unlink(missing_ok=True)
