"""
ScreenStash CLI Management Tool.
Usage:
    python screenstash.py setup       - Configure paths, shortcuts, and startup
    python screenstash.py start       - Start background monitoring service
    python screenstash.py stop        - Stop background monitoring service
    python screenstash.py status      - View background service status & stats
    python screenstash.py dashboard   - Launch desktop dashboard in browser
    python screenstash.py scan        - Scan monitored folder for existing screenshots
"""

import sys
import os
import subprocess
from pathlib import Path

import config
import database as db
from background_service import is_daemon_running, stop_running_daemon
from setup_app import run_setup
from watcher import scan_existing_screenshots


def print_status():
    running = is_daemon_running()
    cfg = config.load_config()
    db.init_db()
    stats = db.get_stats()

    print("=" * 50)
    print("📸 ScreenStash System Status")
    print("=" * 50)
    status_str = "🟢 RUNNING (Active in background)" if running else "⚪ STOPPED"
    print(f"Service Status     : {status_str}")
    print(f"Monitored Folder   : {cfg.get('screenshot_dir')}")
    print(f"Total Screenshots  : {stats.get('total', 0)}")
    print(f"Tasks Detected     : {stats.get('categories', {}).get('Task', 0)}")
    print(f"Events Detected    : {stats.get('categories', {}).get('Event', 0)}")
    print(f"Receipts Detected  : {stats.get('categories', {}).get('Receipt', 0)}")
    print(f"App Data Path      : {config.APP_DATA_DIR}")
    print("=" * 50)


def start_service():
    if is_daemon_running():
        print("[!] ScreenStash background service is already running.")
        return

    print("[*] Starting ScreenStash silent background service...")
    if sys.platform == "win32":
        pythonw = Path(sys.executable).parent / "pythonw.exe"
        exe = str(pythonw) if pythonw.exists() else sys.executable
        target = str(Path(__file__).parent / "background.pyw")
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe, target], cwd=str(Path(__file__).parent), creationflags=flags, close_fds=True)
    else:
        target = str(Path(__file__).parent / "background_service.py")
        subprocess.Popen([sys.executable, target], cwd=str(Path(__file__).parent), close_fds=True)

    print("[✓] Service started in background. New screenshots will trigger 'ScreenStash Saved' popups.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "setup":
        run_setup()
    elif cmd == "start":
        start_service()
    elif cmd == "stop":
        if stop_running_daemon():
            print("[✓] ScreenStash background service stopped.")
        else:
            print("[*] ScreenStash background service is not currently running.")
    elif cmd == "status":
        print_status()
    elif cmd == "dashboard":
        print("[*] Opening ScreenStash Dashboard...")
        subprocess.run([sys.executable, str(Path(__file__).parent / "run_desktop.py")])
    elif cmd == "scan":
        print("[*] Scanning screenshot directory...")
        count = scan_existing_screenshots()
        print(f"[✓] Processed {count} new screenshot(s).")
    else:
        print(f"[!] Unknown command '{cmd}'. Available commands: setup, start, stop, status, dashboard, scan")


if __name__ == "__main__":
    main()
