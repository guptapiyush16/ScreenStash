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
import logging
import subprocess
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

PS_TOAST_SCRIPT = Path(__file__).parent / "send_toast.ps1"


def send_windows_native_toast(title: str, message: str) -> bool:
    """
    Fires the official Windows 10/11 Action Center notification banner
    in the bottom-right corner using PowerShell WinRT API.
    """
    if sys.platform != "win32" or not PS_TOAST_SCRIPT.exists():
        return False

    cmd = [
        "powershell",
        "-WindowStyle", "Hidden",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(PS_TOAST_SCRIPT.resolve()),
        "-Title", title,
        "-Message", message
    ]
    try:
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            close_fds=True
        )
        return True
    except Exception as e:
        logger.debug(f"Could not send native Windows toast: {e}")
        return False


def render_standalone_popup(
    title: str = "ScreenStash Saved",
    message: str = "AI is organizing your screenshot...",
    category: str = "Info",
    duration_ms: int = 3500,
    dashboard_url: str = "http://localhost:8501"
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
            text="Click to view dashboard ↗",
            font=("Segoe UI", 8, "italic"),
            fg=text_muted,
            bg=bg_color,
            cursor="hand2"
        )
        lbl_action.pack(anchor="e")

        def on_click(event=None):
            try:
                webbrowser.open(dashboard_url)
            except Exception:
                pass
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
    dashboard_url: str = "http://localhost:8501"
):
    """
    Main entrypoint:
    Fires exactly ONE notification per event.
    Prioritizes official Windows 10/11 Action Center Toast on Windows.
    Falls back to floating Tkinter card if non-Windows or if toast fails.
    """
    if sys.platform == "win32" and PS_TOAST_SCRIPT.exists():
        # Clean Windows 10/11 Action Center notification
        send_windows_native_toast(title, message)
    else:
        # Cross-platform / fallback floating Tkinter card
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
    p_url = args[4] if len(args) > 4 else "http://localhost:8501"

    render_standalone_popup(p_title, p_msg, p_cat, p_dur, p_url)
