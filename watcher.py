"""
Screenshot folder watcher for ScreenStash.
Uses Watchdog to monitor the OS screenshot folder, debounces rapid events,
and dispatches new images to processor.py.
"""

import os
import time
import threading
import logging
from pathlib import Path
from typing import Set, Callable, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from config import load_config
from processor import process_screenshot
import database as db

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ScreenshotEventHandler(FileSystemEventHandler):
    """Handles new file creation events in the screenshot directory."""

    def __init__(self, callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.callback = callback or process_screenshot
        self._recently_handled: dict[str, float] = {}
        self._lock = threading.Lock()

    def _should_handle(self, file_path_str: str) -> bool:
        """Debounce and check if file has a valid screenshot extension."""
        path = Path(file_path_str)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False

        # Ignore temporary / partial files
        if path.name.startswith(".") or path.name.startswith("~") or path.suffix.lower() == ".tmp":
            return False

        with self._lock:
            now = time.time()
            last_handled = self._recently_handled.get(file_path_str, 0.0)
            if now - last_handled < 4.0:
                return False

            self._recently_handled[file_path_str] = now
            # Prune old entries periodically
            if len(self._recently_handled) > 100:
                self._recently_handled = {k: v for k, v in self._recently_handled.items() if now - v < 60.0}

        return True

    def on_created(self, event):
        if not event.is_directory and self._should_handle(event.src_path):
            logger.info(f"New screenshot detected: {event.src_path}")
            threading.Thread(
                target=self._process_async,
                args=(event.src_path,),
                daemon=True
            ).start()

    def on_modified(self, event):
        # Some OS screenshot tools create an empty file first, then write content on modify
        if not event.is_directory and self._should_handle(event.src_path):
            logger.info(f"Screenshot file updated: {event.src_path}")
            threading.Thread(
                target=self._process_async,
                args=(event.src_path,),
                daemon=True
            ).start()

    def _process_async(self, file_path_str: str):
        try:
            self.callback(file_path_str)
        except Exception as e:
            logger.error(f"Error processing {file_path_str}: {e}", exc_info=True)


class ScreenshotWatcher:
    """Manages the background Watchdog observer."""

    def __init__(self, directory: Optional[str] = None):
        self.config = load_config()
        self.directory = Path(directory or self.config.get("screenshot_dir"))
        self.observer: Optional[Observer] = None
        self.is_active = False

    def start(self):
        """Starts watching the screenshot directory."""
        if self.is_active:
            return

        if not self.directory.exists():
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Could not create screenshot directory {self.directory}: {e}")
                return

        event_handler = ScreenshotEventHandler()
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.directory), recursive=False)
        self.observer.start()
        self.is_active = True
        logger.info(f"ScreenshotWatcher started monitoring: {self.directory}")

    def stop(self):
        """Stops the observer."""
        if self.observer and self.is_active:
            self.observer.stop()
            self.observer.join(timeout=3)
            self.is_active = False
            logger.info("ScreenshotWatcher stopped.")


def scan_existing_screenshots(directory: Optional[str] = None) -> int:
    """
    Scans the folder for existing screenshot images and processes any unrecorded ones.
    Returns number of newly processed items.
    """
    config = load_config()
    target_dir = Path(directory or config.get("screenshot_dir"))
    if not target_dir.exists():
        return 0

    count = 0
    # Sort files by creation time
    image_files: List[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        image_files.extend(target_dir.glob(f"*{ext}"))
        image_files.extend(target_dir.glob(f"*{ext.upper()}"))

    # Process newest first, up to reasonable limit for initial scan
    image_files = sorted(set(image_files), key=lambda p: p.stat().st_mtime, reverse=True)

    for img_path in image_files[:50]:  # Limit initial batch to 50
        try:
            res = process_screenshot(str(img_path))
            if res:
                count += 1
        except Exception as e:
            logger.warning(f"Error scanning {img_path.name}: {e}")

    logger.info(f"Scan complete: {count} screenshots processed from {target_dir}")
    return count


if __name__ == "__main__":
    db.init_db()
    watcher = ScreenshotWatcher()
    watcher.start()
    print(f"[*] Monitoring screenshots in: {watcher.directory}")
    print("[*] Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("\n[*] Stopped watcher.")
