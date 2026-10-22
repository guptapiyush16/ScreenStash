"""
Desktop Launcher for ScreenStash.
Runs the background screenshot watcher and starts the Streamlit dashboard,
automatically opening your browser window.
"""

import sys
import time
import socket
import logging
import webbrowser
import subprocess
from pathlib import Path

import config
import database as db
from watcher import ScreenshotWatcher

logger = logging.getLogger(__name__)


def is_port_in_use(port: int) -> bool:
    """Check if a local port is already open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def main():
    config.setup_logging()
    print("=" * 60)
    print("📸 Starting ScreenStash — Desktop Screenshot-to-Plan")
    print("=" * 60)

    # 1. Initialize SQLite Database
    db.init_db()
    cfg = config.load_config()
    screenshot_dir = cfg.get("screenshot_dir")

    print(f"[*] Monitored Screenshot Folder: {screenshot_dir}")
    print(f"[*] App Data & Database Path   : {config.APP_DATA_DIR}")

    # 2. Start Background Watcher
    watcher = ScreenshotWatcher(screenshot_dir)
    watcher.start()
    print("[*] Background file watcher initialized and active.")

    # 3. Determine Port & URL
    port = 8501
    while is_port_in_use(port):
        port += 1
    dashboard_url = f"http://localhost:{port}"

    # 4. Launch Streamlit Dashboard Process
    app_path = Path(__file__).parent / "app.py"
    cmd = [
        sys.executable,
        "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.serverAddress", "localhost",
        "--theme.base", "dark"
    ]

    print(f"[*] Launching dashboard on {dashboard_url} ...")
    streamlit_proc = subprocess.Popen(cmd)

    # 5. Wait for server to start, then open browser
    time.sleep(2.5)
    try:
        webbrowser.open(dashboard_url)
    except Exception as e:
        print(f"[!] Could not open browser automatically: {e}")

    print("\n[✓] ScreenStash Desktop is running!")
    print(f"[✓] Dashboard URL: {dashboard_url}")
    print("[*] Take a screenshot with Win+PrtScn or Win+Shift+S to test.")
    print("[*] Press Ctrl+C in this console to stop ScreenStash.\n")

    try:
        streamlit_proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Shutting down ScreenStash Desktop...")
        watcher.stop()
        streamlit_proc.terminate()
        streamlit_proc.wait(timeout=3)
        print("[✓] ScreenStash stopped cleanly.")


if __name__ == "__main__":
    main()
