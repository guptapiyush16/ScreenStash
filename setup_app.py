"""
ScreenStash Setup & Deployment Wizard.
Handles:
1. Environment and dependency checks
2. Default screenshot directory auto-detection (including OneDrive support)
3. Database initialization at OS application-data directory
4. Creating Desktop and Start Menu shortcuts
5. Registering ScreenStash in Windows Startup (auto-runs on boot)
6. Launching the silent background service
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

import config
import database as db
from background_service import is_daemon_running, stop_running_daemon


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_windows_startup_dir() -> Path:
    """Returns the Windows user Startup directory (shell:startup)."""
    appdata = os.getenv("APPDATA")
    if appdata:
        startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup.mkdir(parents=True, exist_ok=True)
        return startup
    return Path.home()


def create_windows_shortcut(target_path: str, arguments: str, shortcut_path: Path, description: str):
    """Creates a Windows .lnk shortcut using PowerShell COM object."""
    ps_cmd = f"""
    $WshShell = New-Object -ComObject WScript.Shell;
    $Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}');
    $Shortcut.TargetPath = '{target_path}';
    $Shortcut.Arguments = '{arguments}';
    $Shortcut.WorkingDirectory = '{str(Path(__file__).parent.resolve())}';
    $Shortcut.Description = '{description}';
    $Shortcut.Save();
    """
    try:
        subprocess.run(["powershell", "-Command", ps_cmd], check=True, capture_output=True)
        return True
    except Exception as e:
        return False


def run_setup(auto_start: bool = True):
    print("=" * 65)
    print("[*] ScreenStash Desktop Setup & Deployment")
    print("=" * 65)

    # 1. Check Python
    print(f"[*] Python Version: {sys.version.split()[0]}")

    # 2. Initialize Database & Config
    print("[*] Initializing local database and configuration...")
    db.init_db()
    cfg = config.load_config()
    screenshot_dir = Path(cfg.get("screenshot_dir", str(config.detect_default_screenshot_dir())))

    print(f"[✓] App Data Directory: {config.APP_DATA_DIR}")
    print(f"[✓] Database Path     : {config.DATABASE_PATH}")
    print(f"[✓] Screenshot Folder : {screenshot_dir}")

    # 3. Create Windows Shortcuts (Desktop & Startup)
    if sys.platform == "win32":
        project_dir = Path(__file__).parent.resolve()
        desktop_dir = Path.home() / "Desktop"
        startup_dir = get_windows_startup_dir()

        python_exe = sys.executable
        # Locate pythonw.exe in same directory as python.exe for windowless execution
        pythonw_candidate = Path(python_exe).parent / "pythonw.exe"
        pythonw_exe = str(pythonw_candidate) if pythonw_candidate.exists() else python_exe

        background_script = str(project_dir / "background.pyw")
        run_desktop_script = str(project_dir / "run_desktop.py")

        # 3a. Desktop Shortcut for Dashboard
        desktop_shortcut = desktop_dir / "ScreenStash Dashboard.lnk"
        create_windows_shortcut(
            target_path=python_exe,
            arguments=f'"{run_desktop_script}"',
            shortcut_path=desktop_shortcut,
            description="Open ScreenStash Dashboard"
        )
        print(f"[✓] Created Desktop shortcut: {desktop_shortcut.name}")

        # 3b. Windows Startup Shortcut (Runs silently on boot)
        startup_shortcut = startup_dir / "ScreenStash Background Service.lnk"
        create_windows_shortcut(
            target_path=pythonw_exe,
            arguments=f'"{background_script}"',
            shortcut_path=startup_shortcut,
            description="ScreenStash Background Screenshot Monitor"
        )
        print(f"[✓] Registered in Windows Startup (auto-runs on boot)")

    # 4. Stop any existing daemon instance
    if is_daemon_running():
        print("[*] Restarting existing background daemon...")
        stop_running_daemon()

    # 5. Start the background service now
    if auto_start:
        print("[*] Starting ScreenStash Background Service...")
        if sys.platform == "win32":
            pythonw_candidate = Path(sys.executable).parent / "pythonw.exe"
            exe_to_use = str(pythonw_candidate) if pythonw_candidate.exists() else sys.executable
            bg_target = str(Path(__file__).parent / "background.pyw")
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([exe_to_use, bg_target], cwd=str(Path(__file__).parent), creationflags=flags, close_fds=True)
        else:
            bg_target = str(Path(__file__).parent / "background_service.py")
            subprocess.Popen([sys.executable, bg_target], cwd=str(Path(__file__).parent), close_fds=True)

        print("\n" + "=" * 65)
        print("[+] ScreenStash is successfully deployed and running in the background!")
        print("=" * 65)
        print("[*] How to test it right now:")
        print("   1. Take a screenshot anywhere on your screen (Win+Shift+S or Win+PrtScn).")
        print("   2. You will see a dark-mode popup in the bottom-right corner saying:")
        print("      'ScreenStash Saved - AI is organizing your screenshot...'")
        print("   3. AI will process the screenshot and categorize it as Task, Event, or Receipt.")
        print("   4. Click on the popup to view your organized dashboard!")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    run_setup()
