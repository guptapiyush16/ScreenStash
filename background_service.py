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


def handle_screenshot_event(file_path_str: str):
    """
    Called whenever a new screenshot is detected:
    Delegates to process_screenshot which handles stabilization,
    deduplication, single-toast notifications, OCR, and AI categorization.
    """
    file_name = Path(file_path_str).name
    logger.info(f"Processing new screenshot from background daemon: {file_name}")

    try:
        process_screenshot(file_path_str)
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
        """Record PID to prevent multiple daemon instances."""
        try:
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"Could not write PID file: {e}")

    def remove_pid(self):
        """Remove PID file on clean shutdown."""
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass

    def start(self):
        """Starts the background monitoring loop."""
        self.write_pid()
        self._running = True

        screenshot_dir = self.cfg.get("screenshot_dir")
        logger.info(f"ScreenStash Background Daemon started (PID: {os.getpid()})")
        logger.info(f"Monitoring folder: {screenshot_dir}")

        event_handler = ScreenshotEventHandler(callback=handle_screenshot_event)
        self.watcher = ScreenshotWatcher(screenshot_dir)
        
        # Override the handler to use our custom feedback handler
        from watchdog.observers import Observer
        self.watcher.observer = Observer()
        self.watcher.observer.schedule(event_handler, str(self.watcher.directory), recursive=False)
        self.watcher.observer.start()
        self.watcher.is_active = True

        try:
            while self._running:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self):
        """Stops the daemon and cleans up."""
        self._running = False
        if self.watcher:
            self.watcher.stop()
        self.remove_pid()
        logger.info("ScreenStash Background Daemon stopped.")


def is_daemon_running() -> bool:
    """Checks if a background daemon process is currently running."""
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        return False


def stop_running_daemon() -> bool:
    """Terminates any active background daemon process."""
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        if PID_FILE.exists():
            PID_FILE.unlink()
        return True
    except Exception as e:
        logger.warning(f"Failed to stop daemon PID {pid}: {e}")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return False


if __name__ == "__main__":
    daemon = BackgroundDaemon()
    daemon.start()
