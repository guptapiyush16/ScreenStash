"""
Notification engine for ScreenStash.
Displays a single, clean notification in the bottom-right corner when a
screenshot is detected and organized:
- On Windows: Uses the official native Windows 10/11 Action Center notification banner (with sound chime).
- Non-Windows / Fallback: Uses a sleek borderless dark-mode Tkinter card.
"""

import os
import sys
import time
import base64
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

PS_TOAST_SCRIPT = Path(__file__).parent / "send_toast.ps1"
IS_FROZEN = bool(getattr(sys, "frozen", False))

# Inlined copy of send_toast.ps1 so the packaged sidecar does not depend on a
# data file that PyInstaller never bundled.
_PS_TOAST_TEMPLATE = r"""
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode('__TITLE__')) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode('__MESSAGE__')) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    $appId = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
} catch { }
"""


def _child_process_kwargs() -> dict:
    """
    Spawn helpers from a neutral working directory with a clean PyInstaller
    environment. A child that starts inside (or inherits) the one-file
    _MEIxxxx extraction folder keeps it locked, which makes the bootloader
    show "Failed to remove temporary directory" when the sidecar exits.
    """
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL"):
        env.pop(key, None)
    kwargs = {"cwd": tempfile.gettempdir(), "env": env, "close_fds": True,
              "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def _ps_quote(value: str) -> str:
    """Escape text for a single-quoted PowerShell string literal."""
    return (value or "").replace("'", "''").replace("\r", " ").replace("\n", " ")[:200]


def send_windows_native_toast(title: str, message: str) -> bool:
    """
    Fires the official Windows 10/11 Action Center notification banner
    in the bottom-right corner using the PowerShell WinRT API.
    """
    if sys.platform != "win32":
        return False

    script = _PS_TOAST_TEMPLATE.replace("__TITLE__", _ps_quote(title)).replace("__MESSAGE__", _ps_quote(message))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-NonInteractive",
           "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]
    try:
        subprocess.Popen(cmd, **_child_process_kwargs())
        return True
    except Exception as e:
        logger.debug(f"Could not send native Windows toast: {e}")
        return False


def send_macos_notification(title: str, message: str) -> bool:
    """Native macOS Notification Center banner via osascript."""
    if sys.platform != "darwin":
        return False
    safe = lambda text: (text or "").replace("\\", "\\\\").replace('"', '\\"')[:200]
    script = f'display notification "{safe(message)}" with title "{safe(title)}"'
    try:
        subprocess.Popen(["osascript", "-e", script], **_child_process_kwargs())
        return True
    except Exception as e:
        logger.debug(f"Could not send macOS notification: {e}")
        return False


def render_standalone_popup(
    title: str = "ScreenStash Saved",
    message: str = "AI is organizing your screenshot...",
    category: str = "Info",
    duration_ms: int = 3500,
    dashboard_url: str = ""
):
    """
    Fallback: renders a borderless, top-most, dark-mode toast card directly using Tkinter.
    """
    try:
        import tkinter as tk
    except ImportError:
        return

    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)

        bg_color = "#181825"
        text_primary = "#cdd6f4"
        text_muted = "#a6adc8"
        accent_color = "#89b4fa"
        icon = "📸"

        cat_lower = (category or "").lower()
        if "task" in cat_lower:
            accent_color = "#89b4fa"
            icon = "☑️"
        elif "event" in cat_lower:
            accent_color = "#cba6f7"
            icon = "🗓️"
        elif "receipt" in cat_lower:
            accent_color = "#a6e3a1"
            icon = "💳"
        elif "reference" in cat_lower:
            accent_color = "#f9e2af"
            icon = "📌"

        root.configure(bg=accent_color)

        inner_frame = tk.Frame(root, bg=bg_color, padx=14, pady=10)
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        header_frame = tk.Frame(inner_frame, bg=bg_color)
        header_frame.pack(fill=tk.X, anchor="w")

        lbl_icon = tk.Label(header_frame, text=icon, font=("Segoe UI Emoji", 13), bg=bg_color)
        lbl_icon.pack(side=tk.LEFT, padx=(0, 8))

        lbl_title = tk.Label(
            header_frame,
            text=title,
            font=("Segoe UI", 11, "bold"),
            fg=accent_color,
            bg=bg_color
        )
        lbl_title.pack(side=tk.LEFT)

        lbl_msg = tk.Label(
            inner_frame,
            text=message,
            font=("Segoe UI", 9),
            fg=text_primary,
            bg=bg_color,
            wraplength=290,
            justify=tk.LEFT
        )
        lbl_msg.pack(anchor="w", pady=(3, 4))

        lbl_action = tk.Label(
            inner_frame,
            text="ScreenStash is processing locally",
            font=("Segoe UI", 8, "italic"),
            fg=text_muted,
            bg=bg_color,
            cursor="hand2"
        )
        lbl_action.pack(anchor="e")

        def on_click(event=None):
            try:
                root.destroy()
            except Exception:
                pass

        for widget in (root, inner_frame, header_frame, lbl_icon, lbl_title, lbl_msg, lbl_action):
            widget.bind("<Button-1>", on_click)

        root.update_idletasks()
        width = 330
        height = root.winfo_reqheight()
        if height < 75:
            height = 80

        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()

        x = screen_w - width - 24
        y = screen_h - height - 65
        root.geometry(f"{width}x{height}+{x}+{y}")

        root.lift()
        root.attributes("-topmost", True)
        root.focus_force()

        root.after(duration_ms, root.destroy)
        root.mainloop()

    except Exception as e:
        logger.debug(f"Tkinter popup error: {e}")


def show_saved_toast(
    title: str = "ScreenStash Saved",
    message: str = "AI is organizing your screenshot...",
    category: str = "Info",
    duration_ms: int = 3500,
    dashboard_url: str = ""
):
    """
    Main entrypoint:
    Fires exactly ONE notification per event.
    Prioritizes the native OS notification (Windows Action Center / macOS
    Notification Center). The Tkinter card is only used from source installs,
    never from the packaged sidecar: there sys.executable is the sidecar exe
    itself, and re-launching it would lock its one-file temp folder.
    """
    if send_windows_native_toast(title, message) or send_macos_notification(title, message):
        return
    if IS_FROZEN:
        logger.debug("No native notifier available in packaged build; skipping popup.")
        return
    else:
        # Source-install fallback floating Tkinter card
        notifier_script = str(Path(__file__).resolve())
        cmd = [
            sys.executable,
            notifier_script,
            title,
            message,
            category,
            str(duration_ms),
            dashboard_url
        ]
        try:
            subprocess.Popen(cmd, close_fds=True)
        except Exception as e:
            logger.debug(f"Could not spawn floating card subprocess: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    p_title = args[0] if len(args) > 0 else "ScreenStash Saved"
    p_msg = args[1] if len(args) > 1 else "AI is organizing your screenshot..."
    p_cat = args[2] if len(args) > 2 else "Info"
    p_dur = int(args[3]) if len(args) > 3 else 3500
    p_url = args[4] if len(args) > 4 else ""

    render_standalone_popup(p_title, p_msg, p_cat, p_dur, p_url)
