"""
Configuration and paths for ScreenStash.
All application data (SQLite database, configuration JSON, and logs) are stored
in the OS-specific application data directory to keep the repository clean.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any

# Application metadata
APP_NAME = "ScreenStash"
APP_DIR_NAME = "ScreenStash"
DEFAULT_CLOUD_API_URL = "https://screenstash-cloudapi.onrender.com"
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024


def get_app_data_dir() -> Path:
    """
    Returns the OS-specific application data directory:
    - Windows: %LOCALAPPDATA%/ScreenStash or %APPDATA%/ScreenStash
    - macOS: ~/Library/Application Support/ScreenStash
    - Linux: ~/.local/share/ScreenStash or ~/.screenstash
    """
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
        app_dir = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        app_dir = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        base = os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        app_dir = Path(base) / APP_DIR_NAME

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def detect_default_screenshot_dir() -> Path:
    """
    Auto-detect the default OS screenshot directory.
    On Windows:
    1. Checks OneDrive Screenshots (common in Windows 10/11)
    2. Checks standard %USERPROFILE%/Pictures/Screenshots
    3. Falls back to %USERPROFILE%/Pictures
    """
    user_home = Path.home()

    if sys.platform == "win32":
        # Check environment variable and OneDrive paths
        onedrive = os.getenv("OneDrive") or os.getenv("OneDriveCommercial") or os.getenv("OneDriveConsumer")
        candidate_paths = []
        if onedrive:
            candidate_paths.append(Path(onedrive) / "Pictures" / "Screenshots")

        # Standard Windows Pictures/Screenshots
        candidate_paths.append(user_home / "Pictures" / "Screenshots")
        candidate_paths.append(user_home / "OneDrive" / "Pictures" / "Screenshots")
        candidate_paths.append(user_home / "Pictures")

        for path in candidate_paths:
            if path.exists() and path.is_dir():
                return path

        # Fallback: create standard directory if not exists
        default_dir = user_home / "Pictures" / "Screenshots"
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    elif sys.platform == "darwin":
        # macOS saves screenshots to Desktop by default
        desktop = user_home / "Desktop"
        return desktop if desktop.exists() else user_home

    else:
        # Linux standard screenshots path
        linux_screenshots = user_home / "Pictures" / "Screenshots"
        if linux_screenshots.exists():
            return linux_screenshots
        pictures = user_home / "Pictures"
        return pictures if pictures.exists() else user_home


# Global base paths
APP_DATA_DIR = get_app_data_dir()
CONFIG_FILE_PATH = APP_DATA_DIR / "config.json"
DATABASE_PATH = APP_DATA_DIR / "screenstash.db"
LOG_FILE_PATH = APP_DATA_DIR / "screenstash.log"


# Default settings dictionary
DEFAULT_CONFIG: Dict[str, Any] = {
    "screenshot_dir": str(detect_default_screenshot_dir()),
    "ollama_url": "http://localhost:11434",
    "ollama_model": "gemma3:4b",
    "ai_provider": "offline",
    "cloud_api_url": DEFAULT_CLOUD_API_URL,
    "cloud_consent": False,
    "cloud_installation_id": "",
    "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe" if sys.platform == "win32" else "tesseract",
    "auto_process_new_screenshots": True,
    "file_settle_wait_seconds": 1.5,
    "enable_fallback_heuristic_ai": True,
    "theme": "light",
    "onboarding_complete": False,
    "process_locally": True,
    "start_at_login": False,
    "notify_on_results": True,
}


def load_config() -> Dict[str, Any]:
    """Load settings from config.json or create defaults."""
    if not CONFIG_FILE_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
            # Merge with defaults for any missing keys
            config = DEFAULT_CONFIG.copy()
            config.update(saved)
            return config
    except Exception as e:
        logging.error(f"Error loading config from {CONFIG_FILE_PATH}: {e}")
        return DEFAULT_CONFIG.copy()


def save_config(config_data: Dict[str, Any]) -> None:
    """Save configuration to config.json."""
    try:
        CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving config to {CONFIG_FILE_PATH}: {e}")


def setup_logging() -> None:
    """Configure logging to both file and console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
