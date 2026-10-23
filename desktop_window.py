"""
Native Desktop Window Manager for ScreenStash.
Opens the ScreenStash dashboard inside a true, native desktop application window:
- Primary: Native Win32 / WebView2 window via pywebview (no URL bar, no browser tabs).
- Secondary: Standalone Native App Mode via Microsoft Edge or Google Chrome (--app=...).
- Fallback: System default browser.
"""

import os
import sys
import shutil
import logging
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def find_standalone_browser() -> Optional[list]:
    """
    Locates Microsoft Edge or Google Chrome executable on Windows
    to launch in standalone '--app' mode without any address bar or browser chrome.
    """
    if sys.platform != "win32":
        # Check Linux/macOS for chrome/chromium
        for cmd in ["google-chrome", "chromium", "brave-browser"]:
            path = shutil.which(cmd)
            if path:
                return [path]
        return None

    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in edge_candidates:
        if Path(path).exists():
            return [path]

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in chrome_candidates:
        if Path(path).exists():
            return [path]

    return None


def open_desktop_window(
    url: str,
    title: str = "ScreenStash — Screenshot-to-Plan",
    width: int = 1280,
    height: int = 840,
    prefer_webview: bool = True
):
    """
    Opens the dashboard inside a native, standalone desktop window.
    Hides all browser URLs, navigation bars, and tabs.
    """
    # 1. Try pywebview for a 100% native Win32/WebView2 app window
    if prefer_webview:
        try:
            import webview
            logger.info("Opening dashboard in native pywebview window...")
            window = webview.create_window(
                title=title,
                url=url,
                width=width,
                height=height,
                min_size=(960, 600),
                resizable=True,
                text_select=True,
                confirm_close=False,
            )
            webview.start(private_mode=False)
            return True
        except Exception as e:
            logger.warning(f"pywebview window could not be opened: {e}. Falling back to App Mode.")

    # 2. Try Edge/Chrome standalone App Mode
    browser_bin = find_standalone_browser()
    if browser_bin:
        try:
            cmd = browser_bin + [
                f"--app={url}",
                f"--window-size={width},{height}",
                "--new-window",
                "--disable-features=TranslateUI",
                "--app-id=ScreenStash"
            ]
            logger.info(f"Opening dashboard in standalone App Mode via {browser_bin[0]}...")
            proc = subprocess.Popen(cmd)
            proc.wait()
            return True
        except Exception as e:
            logger.warning(f"App Mode launch failed: {e}. Falling back to default browser.")

    # 3. Last-resort fallback: standard browser
    try:
        print("\n[*] Opening ScreenStash in your default browser...")
        webbrowser.open(url)
        print("[*] ScreenStash is active. Press Ctrl+C in this terminal when you want to close the dashboard.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        return True
    except Exception as e:
        logger.error(f"Failed to open dashboard: {e}")
        return False


if __name__ == "__main__":
    test_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
    open_desktop_window(test_url)
