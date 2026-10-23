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
from background_service import is_daemon_running, stop_running_daemon
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


def ensure_background_daemon_running() -> bool:
    """
    Ensures the 24/7 background screenshot daemon is actively running as an independent,
    detached system process that persists even after the desktop window is closed.
    """
    if is_daemon_running():
        return True

    project_dir = Path(__file__).parent.resolve()
    if sys.platform == "win32":
        pythonw_candidate = Path(sys.executable).parent / "pythonw.exe"
        exe_to_use = str(pythonw_candidate) if pythonw_candidate.exists() else sys.executable
        bg_target = str(project_dir / "background.pyw")
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe_to_use, bg_target], cwd=str(project_dir), creationflags=flags, close_fds=True)
    else:
        bg_target = str(project_dir / "background_service.py")
        subprocess.Popen([sys.executable, bg_target], cwd=str(project_dir), close_fds=True)

    time.sleep(0.8)
    return is_daemon_running()


def main():
    config.setup_logging()
    print("=" * 62)
    print("📸  Starting ScreenStash — Desktop Application")
    print("=" * 62)

    # 1. Initialize SQLite Database & Config
    db.init_db()
    cfg = config.load_config()
    screenshot_dir = cfg.get("screenshot_dir", str(config.detect_default_screenshot_dir()))

    print(f"[*] Screenshot Folder : {screenshot_dir}")
    print(f"[*] App Data Path     : {config.APP_DATA_DIR}")

    # 2. Check Background Monitor & Onboarding
    onboarding_done = cfg.get("onboarding_complete", False)
    if not onboarding_done:
        print("[*] Welcome! First-run onboarding setup will open in the app window.")
    else:
        print("[*] Checking background screenshot monitor...")
        if ensure_background_daemon_running():
            print("[✓] Background screenshot monitor is ACTIVE and watching for screenshots.")
        else:
            print("[!] Background monitor could not be started automatically. Will retry after window opens.")

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
    if not wait_for_server(port, max_seconds=12.0):
        streamlit_proc.terminate()
        raise RuntimeError("ScreenStash dashboard failed to start.")
    time.sleep(1.0)

    print("[✓] Opening ScreenStash native desktop window...")
    print("[*] Close the ScreenStash window when you want to minimize to background.\n")

    try:
        # 6. Launch Native Desktop Window (blocks until window is closed)
        open_desktop_window(
            url=dashboard_url,
            title="ScreenStash — Screenshot-to-Plan",
            width=1280,
            height=840
        )
    except KeyboardInterrupt:
        pass
    finally:
        print("\n" + "=" * 62)
        print("[*] ScreenStash desktop window closed.")
        
        # Free the internal Streamlit web server
        streamlit_proc.terminate()
        try:
            streamlit_proc.wait(timeout=3)
        except Exception:
            streamlit_proc.kill()

        # Reload config in case onboarding was just completed inside the app
        cfg_after = config.load_config()
        if cfg_after.get("onboarding_complete", False):
            ensure_background_daemon_running()
            if is_daemon_running():
                print("[✓] Background screenshot monitor is STILL ACTIVE in the background!")
                print("[*] Any screenshot you take (Win+Shift+S or Win+PrtScn) will be processed.")
                print("[*] Click your Desktop icon or notification anytime to reopen the app.")
            else:
                print("[*] Background monitor is currently idle.")
        print("=" * 62)
        time.sleep(2.0)


if __name__ == "__main__":
    main()
