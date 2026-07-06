from __future__ import annotations

import sys

from tg_listener_process import stop_listeners


def main() -> None:
    stopped = stop_listeners()
    if stopped:
        print(f"Stopped listener process(es): {', '.join(str(pid) for pid in stopped)}")
    else:
        print("No running listener found.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
