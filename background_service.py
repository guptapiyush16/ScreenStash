"""
Always-running background daemon for ScreenStash.
Runs 24/7 silently, monitors the screenshot folder, displays the
'ScreenStash Saved' desktop popup, processes images with AI, and stores results.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from typing import Optional

import config
import database as db
from watcher import ScreenshotEventHandler, ScreenshotWatcher
from processor import process_screenshot
from notifier import show_saved_toast

logger = logging.getLogger(__name__)

PID_FILE = config.APP_DATA_DIR / "screenstash_daemon.pid"
STOP_FILE = config.APP_DATA_DIR / "screenstash_daemon.stop"
CONFIG_POLL_SECONDS = 2.0


def handle_screenshot_event(file_path_str: str):
    """
    Called whenever a new screenshot is detected:
    Delegates to process_screenshot which handles stabilization,
    deduplication, single-toast notifications, OCR, and AI categorization.
    """
    file_name = Path(file_path_str).name
    logger.info(f"Processing new screenshot from background daemon: {file_name}")

    try:
        return process_screenshot(file_path_str)
    except Exception as e:
        logger.error(f"Error handling screenshot {file_path_str}: {e}", exc_info=True)


class BackgroundDaemon:
    """Manages the background watcher lifecycle and PID tracking."""

    def __init__(self):
        config.setup_logging()
        db.init_db()
        self.cfg = config.load_config()
        self.watcher: Optional[ScreenshotWatcher] = None
        self._running = False

    def write_pid(self):
        """Atomically record PID so two watcher processes cannot start together."""
        try:
            fd = os.open(PID_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            if not is_daemon_running():
                PID_FILE.unlink(missing_ok=True)
                return self.write_pid()
            logger.info("ScreenStash watcher is already running")
            return False
        except Exception as e:
            logger.warning(f"Could not write PID file: {e}")
            return False

    def remove_pid(self):
        """Remove PID file on clean shutdown."""
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass

    def _normalize(self, folder: Optional[str]) -> str:
        try:
            return str(Path(folder).expanduser().resolve()) if folder else ""
        except Exception:
            return folder or ""

    def _watch(self, folder: str, first_start: bool) -> None:
        """(Re)point the watcher at a folder. Only new screenshots are processed."""
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self.watched_dir = self._normalize(folder)
        watcher = ScreenshotWatcher(folder)
        # Never create folders from a half-typed path in Settings; only the
        # very first start may create the OS default Screenshots folder.
        if watcher.start(callback=handle_screenshot_event, create_if_missing=first_start):
            self.watcher = watcher
            logger.info(f"Monitoring folder: {folder}")

    def _reload_if_folder_changed(self) -> None:
        folder = config.load_config().get("screenshot_dir")
        normalized = self._normalize(folder)
        if normalized != self.watched_dir or (self.watcher is None and folder and Path(folder).is_dir()):
            if normalized != self.watched_dir:
                logger.info(f"Screenshot folder changed: {self.watched_dir} -> {normalized}")
            self._watch(folder, first_start=False)

    def start(self):
        """Starts the background monitoring loop."""
        if not self.write_pid():
            return
        STOP_FILE.unlink(missing_ok=True)
        self._running = True
        self.watched_dir = ""

        logger.info(f"ScreenStash Background Daemon started (PID: {os.getpid()})")
        self._watch(self.cfg.get("screenshot_dir"), first_start=True)

        last_poll = time.time()
        try:
            while self._running:
                time.sleep(0.5)
                if STOP_FILE.exists():
                    logger.info("Stop requested by ScreenStash desktop app.")
                    break
                if time.time() - last_poll >= CONFIG_POLL_SECONDS:
                    last_poll = time.time()
                    self._reload_if_folder_changed()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop()

    def stop(self):
        """Stops the daemon and cleans up."""
        self._running = False
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        self.remove_pid()
        STOP_FILE.unlink(missing_ok=True)
        logger.info("ScreenStash Background Daemon stopped.")


def is_daemon_running() -> bool:
    """Checks if a background daemon process is currently running."""
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        import psutil
        if not psutil.pid_exists(pid):
            PID_FILE.unlink(missing_ok=True)
            return False
        process = psutil.Process(pid)
        name = process.name().lower()
        command = " ".join(process.cmdline()).lower()
        return "screenstash-sidecar" in name or "background_service.py" in command or "background.pyw" in command
    except Exception:
        return False


def stop_running_daemon() -> bool:
    """
    Asks the background daemon to exit on its own (stop-flag file) so the
    PyInstaller bootloader can clean up its _MEI temp folder. A hard kill is
    only used as a last resort.
    """
    if not PID_FILE.exists():
        return False
    pid = None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if not is_daemon_running():
            PID_FILE.unlink(missing_ok=True)
            return False
        STOP_FILE.touch()
        deadline = time.time() + 6.0
        while time.time() < deadline:
            if not PID_FILE.exists():
                return True
            time.sleep(0.25)
        logger.warning(f"Daemon PID {pid} did not stop gracefully; terminating.")
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        PID_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.warning(f"Failed to stop daemon PID {pid}: {e}")
        PID_FILE.unlink(missing_ok=True)
        STOP_FILE.unlink(missing_ok=True)
        return False


if __name__ == "__main__":
    daemon = BackgroundDaemon()
    daemon.start()
