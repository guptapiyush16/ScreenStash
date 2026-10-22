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
from background_service import is_daemon_running
from desktop_window import open_desktop_window

logger = logging.getLogger(__name__)


def is_port_in_use(port: int) -> bool:
    """Check if a local port is already open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def wait_for_server(port: int, max_seconds: float = 10.0) -> bool:
    """Poll until server socket is accepting connections."""
    start = time.time()
    while time.time() - start < max_seconds:
        if is_port_in_use(port):
            return True
        time.sleep(0.2)
    return False


def main():
    config.setup_logging()
    print("=" * 60)
    print("📸 Starting ScreenStash — Desktop Application")
    print("=" * 60)

    # 1. Initialize SQLite Database
    db.init_db()
    cfg = config.load_config()
    screenshot_dir = cfg.get("screenshot_dir")

    print(f"[*] Monitored Screenshot Folder: {screenshot_dir}")
    print(f"[*] App Data & Database Path   : {config.APP_DATA_DIR}")

    # 2. Check Background Watcher
    watcher = None
    if is_daemon_running():
        print("[*] Background daemon is already active. Skipping duplicate watcher.")
    else:
        watcher = ScreenshotWatcher(screenshot_dir)
        watcher.start()
        print("[*] Local background file watcher initialized.")

    # 3. Determine Port & URL
    port = 8501
    while is_port_in_use(port):
        port += 1
    dashboard_url = f"http://localhost:{port}"

    # 4. Launch Streamlit Dashboard Process (Hidden/Headless)
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

    print(f"[*] Launching desktop engine on local port {port}...")
    streamlit_proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" and not sys.stdout.isatty() else 0
    )

    # 5. Wait for server socket to be ready
    wait_for_server(port, max_seconds=10.0)
    time.sleep(1.0)

    print("[✓] Opening ScreenStash native desktop window...")
    print("[*] Close the ScreenStash window to exit.\n")

    try:
        # 6. Launch Native Desktop Window (blocks until window is closed)
        open_desktop_window(
            url=dashboard_url,
            title="ScreenStash",
            width=1280,
            height=840
        )
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[*] Shutting down ScreenStash Desktop...")
        if watcher:
            watcher.stop()
        streamlit_proc.terminate()
        try:
            streamlit_proc.wait(timeout=3)
        except Exception:
            streamlit_proc.kill()
        print("[✓] ScreenStash exited cleanly.")



if __name__ == "__main__":
    main()
