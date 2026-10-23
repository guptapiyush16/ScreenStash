"""
ScreenStash Standalone Executable Builder.
Uses PyInstaller to package ScreenStash into a standalone Windows application (.exe)
that users can run without installing Python.
"""

import sys
import subprocess
from pathlib import Path

def build():
    print("=" * 60)
    print("📦 Building Standalone ScreenStash Windows Executable")
    print("=" * 60)

    try:
        import PyInstaller
    except ImportError:
        print("[*] PyInstaller not found. Installing pyinstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    project_dir = Path(__file__).parent.resolve()
    entry_point = project_dir / "run_desktop.py"

    # PyInstaller arguments
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ScreenStash",
        "--onedir",             # Faster launch and easier updates than onefile for webview apps
        "--windowed",           # Hide terminal window for GUI
        "--noconfirm",
        "--clean",
        f"--icon={project_dir / 'app_icon.ico'}",
        f"--add-data={project_dir / 'app_icon.ico'};.",
        f"--add-data={project_dir / 'app_icon.png'};.",
        f"--add-data={project_dir / 'app.py'};.",
        f"--add-data={project_dir / 'background_service.py'};.",
        f"--add-data={project_dir / 'background.pyw'};.",
        f"--add-data={project_dir / 'desktop_window.py'};.",
        f"--add-data={project_dir / 'notifier.py'};.",
        f"--add-data={project_dir / 'processor.py'};.",
        f"--add-data={project_dir / 'watcher.py'};.",
        f"--add-data={project_dir / 'database.py'};.",
        f"--add-data={project_dir / 'models.py'};.",
        f"--add-data={project_dir / 'config.py'};.",
        f"--add-data={project_dir / 'send_toast.ps1'};.",
        "--hidden-import=streamlit",
        "--hidden-import=watchdog",
        "--hidden-import=webview",
        "--hidden-import=PIL",
        "--hidden-import=pytesseract",
        "--hidden-import=pydantic",
        str(entry_point)
    ]

    print("[*] Executing PyInstaller command:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    print("\n[✓] Build completed! Standalone binary is located in dist/ScreenStash/ScreenStash.exe")

if __name__ == "__main__":
    build()
