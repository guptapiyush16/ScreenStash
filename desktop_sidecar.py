"""Packaged ScreenStash processing sidecar for the Tauri desktop app."""

import sys

from background_service import BackgroundDaemon, stop_running_daemon
from screenstash import setup_ai
from watcher import scan_existing_screenshots


def main() -> int:
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
    if command == "start":
        BackgroundDaemon().start()
        return 0
    if command == "stop":
        return 0 if stop_running_daemon() else 1
    if command == "scan":
        print(f"Processed {scan_existing_screenshots()} screenshot(s).")
        return 0
    if command == "setup-ai":
        setup_ai()
        return 0
    print(f"Unsupported sidecar command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
