"""
ScreenStash — Personalized Desktop Dashboard.
Implements the editorial, high-fidelity light workspace aesthetic matching the
design mockups across Overview, Tasks, Calendar, References, and All Screenshots views.
Includes the full sidebar navigation and the Settings preferences modal matching photos 1, 2, and 3.
"""

import os
import sys
import json
import time
import getpass
import calendar
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional

import streamlit as st
from PIL import Image

import config
import database as db
from models import Category, ProcessStatus, ScreenshotRecord
from processor import process_screenshot
from watcher import ScreenshotWatcher, scan_existing_screenshots
from background_service import is_daemon_running, stop_running_daemon
import subprocess
import html
from ai_engine import MODEL_CHOICES, model_is_available

# 1. Page Configuration
_icon_path = Path(__file__).parent / "app_icon.png"
_page_icon = str(_icon_path) if _icon_path.exists() else "📸"

st.set_page_config(
    page_title="ScreenStash — Your Workspace",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Design System & CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Global Typography & Canvas */
    html, body, [class*="css"], .stApp {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: #fbfbfa !important;
        color: #18181b !important;
    }

    /* Hide Streamlit Web Chrome for Native Desktop Look */
    #MainMenu { visibility: hidden !important; display: none !important; }
    header[data-testid="stHeader"] { visibility: hidden !important; height: 0 !important; }
    footer { visibility: hidden !important; display: none !important; }
    div[data-testid="stDecoration"] { display: none !important; }
    div[data-testid="stStatusWidget"] { display: none !important; }
    .stDeployButton, [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px !important;
    }

    /* Sidebar Styling Matching Photo 2 */
    section[data-testid="stSidebar"] {
        background-color: #f7f6f2 !important;
        border-right: 1px solid #ebe9e1 !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem !important;
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
    }

    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 24px;
        padding-bottom: 8px;
    }
    .sidebar-logo-icon {
        width: 24px;
        height: 24px;
        background: #e4e4e7;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
    }
    .sidebar-brand-name {
        font-size: 16px;
        font-weight: 700;
        color: #18181b;
        letter-spacing: -0.01em;
    }

    .sidebar-section-title {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #a1a1aa;
        margin-top: 18px;
        margin-bottom: 8px;
    }

    .nav-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 7px 10px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        color: #52525b;
        margin-bottom: 2px;
        text-decoration: none;
        cursor: pointer;
        transition: background 0.15s ease, color 0.15s ease;
    }
    .nav-item:hover {
        background: #eeede8;
        color: #18181b;
    }
    .nav-item.active {
        background: #eaf5d8;
        color: #27272a;
        font-weight: 600;
    }
    .nav-left {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .nav-pill {
        font-size: 11px;
        font-weight: 600;
        padding: 1px 7px;
        border-radius: 10px;
        background: #e4e4e7;
        color: #52525b;
    }
    .nav-pill-active {
        background: #d9ecc1;
        color: #365314;
    }

    .smart-dot-peach { width: 6px; height: 6px; border-radius: 50%; background: #f97316; }
    .smart-dot-purple { width: 6px; height: 6px; border-radius: 50%; background: #a855f7; }
    .smart-dot-green { width: 6px; height: 6px; border-radius: 50%; background: #10b981; }

    /* Bottom Stash Device Card */
    .stash-device-card {
        background: #f0f3ea;
        border: 1px solid #e1e7d5;
        border-radius: 12px;
        padding: 14px;
        margin-top: 30px;
        margin-bottom: 14px;
    }
    .stash-device-title {
        font-size: 12px;
        font-weight: 700;
        color: #27272a;
        margin-bottom: 4px;
    }
    .stash-device-text {
        font-size: 11px;
        color: #71717a;
        line-height: 1.4;
        margin-bottom: 8px;
    }
    .stash-device-status {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 600;
        color: #15803d;
    }

    .settings-btn-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 10px;
        border-radius: 8px;
        font-size: 13px;
        color: #52525b;
        cursor: pointer;
        border-top: 1px solid #ebe9e1;
        margin-top: 6px;
    }
    .settings-btn-row:hover {
        background: #eeede8;
        color: #18181b;
    }

    .profile-row {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 0;
        margin-top: 10px;
        border-top: 1px solid #ebe9e1;
    }
    .profile-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #fed7aa;
        color: #9a3412;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 12px;
    }

    /* Workspace Greeting Header */
    .greeting-kicker {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #4d7c0f;
        margin-bottom: 4px;
    }
    .greeting-dot {
        width: 7px;
        height: 7px;
        background-color: #84cc16;
        border-radius: 50%;
        display: inline-block;
    }
    .greeting-title {
        font-size: 30px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #18181b;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .greeting-star {
        color: #84cc16;
        font-size: 26px;
    }
    .greeting-subtitle {
        font-size: 14px;
        color: #71717a;
        margin-top: 4px;
        margin-bottom: 24px;
    }

    /* Today Floating Badge */
    .today-badge-card {
        background: #ffffff;
        border: 1px solid #e8e6df;
        border-radius: 12px;
        padding: 8px 14px;
        display: inline-flex;
        align-items: center;
        gap: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .today-circle {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        color: #16a34a;
    }

    /* KPI / Metric Cards */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e8e6df;
        border-radius: 16px;
        padding: 18px 20px;
        height: 100%;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        position: relative;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .kpi-card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border-color: #dcd9cf;
    }
    .kpi-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;
    }
    .kpi-label {
        font-size: 12px;
        font-weight: 500;
        color: #71717a;
    }
    .kpi-icon-box {
        width: 28px;
        height: 28px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
    }
    .kpi-icon-green { background: #f0fdf4; color: #16a34a; }
    .kpi-icon-peach { background: #fff7ed; color: #ea580c; }
    .kpi-icon-purple { background: #faf5ff; color: #9333ea; }
    .kpi-icon-lavender { background: #f5f3ff; color: #7c3aed; }

    .kpi-value-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 12px;
    }
    .kpi-num {
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #18181b;
        line-height: 1;
    }
    .kpi-subtext {
        font-size: 11px;
        color: #a1a1aa;
    }
    .kpi-footer-status {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        color: #71717a;
        padding-top: 8px;
        border-top: 1px solid #f4f4f5;
    }
    .kpi-bar-green {
        width: 14px;
        height: 3px;
        background: #84cc16;
        border-radius: 2px;
    }
    .kpi-dot-peach {
        width: 6px;
        height: 6px;
        background: #f97316;
        border-radius: 50%;
    }
    .kpi-dot-purple {
        width: 6px;
        height: 6px;
        background: #a855f7;
        border-radius: 50%;
    }

    /* Section Cards (Editorial White Boxes) */
    .section-card {
        background: #ffffff;
        border: 1px solid #e8e6df;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        margin-bottom: 24px;
    }
    .section-tag {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #71717a;
        margin-bottom: 4px;
    }
    .section-title-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
    }
    .section-title {
        font-size: 18px;
        font-weight: 700;
        color: #18181b;
        letter-spacing: -0.01em;
        margin: 0;
    }
    .section-link {
        font-size: 12px;
        color: #71717a;
        text-decoration: none;
        cursor: pointer;
    }

    /* Calendar Grid */
    .cal-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        margin-bottom: 16px;
    }
    .cal-th {
        font-size: 11px;
        font-weight: 600;
        color: #a1a1aa;
        text-align: center;
        padding: 6px 0;
    }
    .cal-td {
        text-align: center;
        padding: 8px 0;
        font-size: 12px;
        color: #52525b;
        position: relative;
    }
    .cal-td.muted { color: #d4d4d8; }
    .cal-td.today-box {
        border: 1.5px solid #84cc16;
        border-radius: 8px;
        background: #f7fee7;
        font-weight: 700;
        color: #3f6212;
    }
    .cal-dot {
        position: absolute;
        bottom: 2px;
        left: 50%;
        transform: translateX(-50%);
        width: 4px;
        height: 4px;
        border-radius: 50%;
    }
    .cal-dot-deadline { background-color: #ef4444; }
    .cal-dot-event { background-color: #10b981; }
    .cal-dot-review { background-color: #a855f7; }

    /* Next Deadline Banner inside Calendar Card */
    .next-deadline-banner {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 12px;
        padding: 12px 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .deadline-title {
        font-size: 13px;
        font-weight: 600;
        color: #166534;
    }
    .deadline-meta {
        font-size: 11px;
        color: #15803d;
    }

    /* Up Next Task Card */
    .up-next-task {
        background: #fafaf9;
        border: 1px solid #ebe9e1;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 14px;
        display: flex;
        gap: 16px;
        align-items: flex-start;
    }
    .date-chip-peach {
        background: #ffedd5;
        border: 1px solid #fed7aa;
        border-radius: 10px;
        width: 50px;
        height: 52px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .date-chip-num {
        font-size: 18px;
        font-weight: 700;
        color: #9a3412;
        line-height: 1;
    }
    .date-chip-month {
        font-size: 9px;
        font-weight: 700;
        text-transform: uppercase;
        color: #c2410c;
        margin-top: 2px;
    }

    .badge-peach-pill {
        background: #ffedd5;
        color: #9a3412;
        font-size: 10px;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 4px;
    }
    .source-chip {
        font-size: 11px;
        color: #71717a;
        background: #ffffff;
        border: 1px solid #e8e6df;
        padding: 2px 8px;
        border-radius: 6px;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        margin-top: 8px;
    }

    /* Action Checklist Items */
    .action-item-row {
        background: #ffffff;
        border: 1px solid #f4f4f5;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        transition: border-color 0.15s ease;
    }
    .action-item-row:hover {
        border-color: #e4e4e7;
    }
    .action-item-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .action-item-title {
        font-size: 13px;
        font-weight: 600;
        color: #18181b;
    }
    .action-item-sub {
        font-size: 11px;
        color: #71717a;
        margin-top: 2px;
    }

    /* Recently Organized Items */
    .organized-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 10px 0;
        border-bottom: 1px solid #f4f4f5;
    }
    .organized-left {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .thumb-pill {
        width: 44px;
        height: 44px;
        border-radius: 8px;
        background: #f4f4f5;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 9px;
        font-weight: 700;
        text-transform: uppercase;
        color: #52525b;
        text-align: center;
        padding: 4px;
        flex-shrink: 0;
    }
    .thumb-lavender { background: #f3e8ff; color: #7e22ce; }
    .thumb-peach { background: #ffedd5; color: #c2410c; }
    .thumb-green { background: #dcfce7; color: #15803d; }

    /* Evidence Trail Quotes */
    .evidence-quote-box {
        background: #f4f4f5;
        border-radius: 6px;
        padding: 4px 10px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #52525b;
    }

    /* Dark Status Card (Photo 3) */
    .dark-settings-card {
        background: #09090b;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 24px;
        color: #ffffff;
    }
    .dark-status-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
    }
    .dark-status-row:not(:last-child) {
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .dark-icon-box {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
    }
    .dark-icon-green {
        background: #e7f5e9;
        color: #166534;
    }
    .dark-icon-white {
        background: #f4f4f5;
        color: #18181b;
    }
    .badge-pill-connected {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        font-size: 11px;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 20px;
    }
    .badge-pill-ready {
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        font-size: 11px;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 20px;
    }
    .badge-pill-toggle {
        background: #27272a;
        color: #f4f4f5;
        font-size: 11px;
        font-weight: 700;
        padding: 5px 14px;
        border-radius: 20px;
    }

    /* Preferences List (Photo 1) */
    .pref-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 0;
        border-bottom: 1px solid #ebe9e1;
    }
    .pref-label {
        font-size: 14px;
        color: #18181b;
        font-weight: 500;
    }
    .pref-val {
        font-size: 13px;
        font-family: monospace;
        color: #18181b;
        font-weight: 600;
    }

    /* Concept Preview Footer */
    .workspace-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 24px;
        border-top: 1px solid #ebe9e1;
        margin-top: 40px;
        font-size: 12px;
        color: #a1a1aa;
    }
</style>
""", unsafe_allow_html=True)

# 3. Initialize DB and Config
db.init_db()
app_cfg = config.load_config()


def start_background_service() -> None:
    """Start the watcher without opening another dashboard window."""
    if is_daemon_running():
        return
    target = Path(__file__).parent / ("background.pyw" if sys.platform == "win32" else "background_service.py")
    executable = Path(sys.executable).parent / "pythonw.exe" if sys.platform == "win32" else Path(sys.executable)
    if sys.platform == "win32" and not executable.exists():
        executable = Path(sys.executable)
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen([str(executable), str(target)], cwd=str(Path(__file__).parent), creationflags=flags, close_fds=True)


def show_onboarding() -> None:
    """First-run setup: only collect the folder and explicit background consent."""
    st.markdown(
        "<div style='max-width:760px;margin:5vh auto 0;'>"
        "<div class='greeting-kicker'><span class='greeting-dot'></span>WELCOME TO SCREENSTASH</div>"
        "<h1 style='font-size:42px;margin:12px 0 8px;'>Your screenshots can remember for you.</h1>"
        "<p style='font-size:16px;color:#71717a;line-height:1.7;'>"
        "ScreenStash watches the folder where your screenshots already go, waits until each image is fully written, "
        "and turns it into a task, event, receipt, reference, or other useful note. "
        "<strong>Screenshots may contain private information.</strong> Processing stays on this device.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    with st.form("first_run_onboarding"):
        detected = str(config.detect_default_screenshot_dir())
        screenshot_dir = st.text_input("Where are your screenshots saved?", value=app_cfg.get("screenshot_dir", detected))
        st.info(
            "AI processing is local. Choose a model below. ScreenStash uses Ollama when it is available; "
            "otherwise its offline OCR/heuristic fallback still works. You can run "
            "`python screenstash.py setup-ai` later to download the model."
        )
        model_label = st.selectbox(
            "Local AI model",
            options=list(MODEL_CHOICES),
            index=0,
            help="This only chooses the model family. ScreenStash manages the model request for you.",
        )
        start_at_login = False
        if sys.platform == "win32":
            start_at_login = st.checkbox(
                "Start ScreenStash when I log in",
                value=False,
                help="Optional. ScreenStash will not add itself to startup unless you explicitly enable this.",
            )
        else:
            st.caption("Login startup is optional and can be enabled later from your operating system's login-items settings.")
        consent = st.checkbox(
            "I understand screenshots may contain private information and will be processed locally.",
            value=False,
        )
        submitted = st.form_submit_button("Finish setup and start watching", type="primary")
        if submitted:
            if not consent:
                st.error("Please confirm the local/private-data notice before continuing.")
            elif not screenshot_dir.strip():
                st.error("Choose a screenshot folder before continuing.")
            else:
                selected_dir = Path(screenshot_dir).expanduser()
                selected_dir.mkdir(parents=True, exist_ok=True)
                updated = dict(app_cfg)
                updated.update({
                    "screenshot_dir": str(selected_dir),
                    "process_locally": True,
                    "ollama_model": MODEL_CHOICES[model_label],
                    "start_at_login": start_at_login,
                    "onboarding_complete": True,
                })
                config.save_config(updated)
                if start_at_login and sys.platform == "win32":
                    from setup_app import get_windows_startup_dir, create_windows_shortcut
                    startup = get_windows_startup_dir() / "ScreenStash Background Service.lnk"
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    create_windows_shortcut(
                        str(pythonw if pythonw.exists() else sys.executable),
                        f'"{Path(__file__).parent / "background.pyw"}"',
                        startup,
                        "ScreenStash Background Screenshot Monitor",
                    )
                start_background_service()
                st.success("ScreenStash is ready and watching in the background.")
                time.sleep(0.5)
                st.rerun()


if not app_cfg.get("onboarding_complete", False):
    show_onboarding()
    st.stop()

# Personalize greeting
raw_user = getpass.getuser()
user_name = raw_user.split('.')[0].capitalize() if raw_user else "Sam"
hour = datetime.now().hour
greeting_prefix = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
today_formatted = datetime.now().strftime("%a, %b %d")

# Initialize active view state
if "active_view" not in st.session_state:
    st.session_state.active_view = "Overview"


# 4. Settings Dialog matching Photos 1 & 3
@st.dialog("Your preferences")
def show_settings_modal():
    screenshot_dir = app_cfg.get("screenshot_dir", str(config.detect_default_screenshot_dir()))
    short_dir = "~/Pictures/Screenshots" if "Screenshots" in screenshot_dir else screenshot_dir
    daemon_active = is_daemon_running()

    # --- PHOTO 3: Dark Status Card ---
    st.markdown(f"""
    <div class="dark-settings-card">
        <!-- Row 1: Screenshots folder -->
        <div class="dark-status-row">
            <div style="display: flex; align-items: center; gap: 14px;">
                <div class="dark-icon-box dark-icon-green">📁</div>
                <div>
                    <div style="font-size: 14px; font-weight: 700; color: #f4f4f5;">Screenshots folder</div>
                    <div style="font-size: 12px; color: #a1a1aa; font-family: monospace;">{short_dir}</div>
                </div>
            </div>
            <span class="badge-pill-connected">Connected</span>
        </div>

        <!-- Row 2: On-device AI -->
        <div class="dark-status-row">
            <div style="display: flex; align-items: center; gap: 14px;">
                <div class="dark-icon-box dark-icon-green">⚙️</div>
                <div>
                    <div style="font-size: 14px; font-weight: 700; color: #f4f4f5;">On-device AI</div>
                    <div style="font-size: 12px; color: #a1a1aa;">{app_cfg.get("ollama_model", "gemma3:4b")} • Processing locally</div>
                </div>
            </div>
            <span class="badge-pill-ready">{"Ready" if model_is_available(app_cfg.get("ollama_model", "gemma3:4b"), app_cfg.get("ollama_url", "http://localhost:11434")) else "Download needed"}</span>
        </div>

        <!-- Row 3: Background monitoring -->
        <div class="dark-status-row">
            <div style="display: flex; align-items: center; gap: 14px;">
                <div class="dark-icon-box dark-icon-white">🖥️</div>
                <div>
                    <div style="font-size: 14px; font-weight: 700; color: #f4f4f5;">Background monitoring</div>
                    <div style="font-size: 12px; color: #a1a1aa;">Automatically organize new screenshots</div>
                </div>
            </div>
            <span class="badge-pill-toggle">{"Active" if daemon_active else "Paused / Active"}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- PHOTO 1: Preferences Controls ---
    st.markdown("""
    <div style="font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #71717a; margin-bottom: 2px;">SCREENSTASH</div>
    <div style="font-size: 20px; font-weight: 700; color: #18181b; margin-bottom: 4px;">Your preferences</div>
    <div style="font-size: 12px; color: #71717a; margin-bottom: 16px;">These controls represent settings for the local-first desktop app.</div>
    """, unsafe_allow_html=True)

    # Watched screenshot folder row
    col_w1, col_w2 = st.columns([6, 4])
    with col_w1:
        st.markdown("<div class='pref-label'>Watched screenshot folder</div>", unsafe_allow_html=True)
    with col_w2:
        screenshot_dir = st.text_input(
            "Watched screenshot folder",
            value=screenshot_dir,
            label_visibility="collapsed",
            key="settings_screenshot_dir",
        )
    st.markdown("<hr style='border:0; border-top:1px solid #ebe9e1; margin: 10px 0;'>", unsafe_allow_html=True)

    # Process on this device
    col_p1, col_p2 = st.columns([8, 2])
    with col_p1:
        st.markdown("<div class='pref-label'>Process on this device</div>", unsafe_allow_html=True)
    with col_p2:
        proc_device = st.checkbox(
            "Process on this device",
            value=app_cfg.get("process_locally", True),
            label_visibility="collapsed",
            key="chk_proc_dev",
        )
    st.markdown("<hr style='border:0; border-top:1px solid #ebe9e1; margin: 10px 0;'>", unsafe_allow_html=True)

    # Notify for deadlines
    col_n1, col_n2 = st.columns([8, 2])
    with col_n1:
        st.markdown("<div class='pref-label'>Notify for deadlines</div>", unsafe_allow_html=True)
    with col_n2:
        notify_deadlines = st.checkbox(
            "Notify for results",
            value=app_cfg.get("notify_on_results", True),
            label_visibility="collapsed",
            key="chk_notify",
        )
    st.markdown("<hr style='border:0; border-top:1px solid #ebe9e1; margin: 10px 0;'>", unsafe_allow_html=True)

    # Start at login
    col_l1, col_l2 = st.columns([8, 2])
    with col_l1:
        st.markdown("<div class='pref-label'>Start at login</div>", unsafe_allow_html=True)
    with col_l2:
        start_login = st.checkbox(
            "Start at login",
            value=app_cfg.get("start_at_login", False),
            label_visibility="collapsed",
            key="chk_login",
        )
    st.markdown("<hr style='border:0; border-top:1px solid #ebe9e1; margin: 10px 0;'>", unsafe_allow_html=True)

    st.caption("ScreenStash uses these settings on this device. Screenshots and extracted text stay local.")

    col_btn_left, col_btn_right = st.columns([7, 3])
    with col_btn_right:
        if st.button("Done", type="primary", use_container_width=True):
            updated = dict(app_cfg)
            updated.update({
                "screenshot_dir": screenshot_dir,
                "process_locally": proc_device,
                "notify_on_results": notify_deadlines,
                "start_at_login": start_login,
            })
            config.save_config(updated)
            st.rerun()


# 5. Sidebar Navigation Matching Photo 2
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-logo-icon">📊</div>
        <div class="sidebar-brand-name">screenstash</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">YOUR WORKSPACE</div>', unsafe_allow_html=True)

    # Sidebar Navigation items
    views = [
        ("Overview", "📊", None),
        ("Tasks", "☑", 4),
        ("Calendar", "📅", 2),
        ("References", "📁", None),
        ("All screenshots", "🖼️", None)
    ]

    for name, icon, badge in views:
        is_active = (st.session_state.active_view == name)
        active_cls = "active" if is_active else ""
        badge_html = f'<span class="nav-pill { "nav-pill-active" if is_active else "" }">{badge}</span>' if badge else ""
        
        # Streamlit button for each view styled cleanly
        btn_label = f"{icon}  {name}"
        if badge:
            btn_label += f" ({badge})"
            
        if st.button(btn_label, key=f"nav_{name}", use_container_width=True, type="primary" if is_active else "secondary"):
            st.session_state.active_view = name
            st.rerun()

    st.markdown('<div class="sidebar-section-title">SMART VIEWS</div>', unsafe_allow_html=True)

    smart_views = [
        ("Due soon", "smart-dot-peach", 2, "Tasks"),
        ("Needs review", "smart-dot-purple", 2, "Overview"),
        ("Confirmed", "smart-dot-green", 5, "All screenshots")
    ]

    for s_name, dot_cls, s_badge, target_view in smart_views:
        if st.button(f"●  {s_name} ({s_badge})", key=f"smart_{s_name}", use_container_width=True):
            st.session_state.active_view = target_view
            st.rerun()

    # Stash Device Status Card
    daemon_status = is_daemon_running()
    st.markdown(f"""
    <div class="stash-device-card">
        <div style="font-size: 16px; margin-bottom: 4px;">🌐</div>
        <div class="stash-device-title">Your stash, on this device</div>
        <div class="stash-device-text">Your screenshots are processed locally and linked back to their original files.</div>
        <div class="stash-device-status">
            <span class="smart-dot-green"></span>
            <span>{"Watching in background" if daemon_status else "Background watcher stopped"}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Settings Button -> Triggers show_settings_modal
    if st.button("⚙️  Settings  ↗", key="open_settings_btn", use_container_width=True):
        show_settings_modal()

    # User Profile Row
    st.markdown(f"""
    <div class="profile-row">
        <div class="profile-avatar">{user_name[0]}</div>
        <div style="flex-grow: 1;">
            <div style="font-size: 12px; font-weight: 700; color: #18181b;">{user_name}'s workspace</div>
            <div style="font-size: 10px; color: #71717a;">Personal stash</div>
        </div>
        <div style="color: #a1a1aa; font-size: 14px; cursor: pointer;">•••</div>
    </div>
    """, unsafe_allow_html=True)


# 6. Top Header & Action Row
col_top_left, col_top_right = st.columns([6, 4])
with col_top_left:
    st.markdown(f'<div class="breadcrumb-text">Your workspace  /  <span class="breadcrumb-active">{st.session_state.active_view}</span></div>', unsafe_allow_html=True)
with col_top_right:
    col_search, col_add = st.columns([3, 1.8])
    with col_search:
        search_query = st.text_input("Search", placeholder="Search screenshots... ⌘K", label_visibility="collapsed")
    with col_add:
        with st.popover("+ Add screenshot"):
            uploaded_file = st.file_uploader("Upload screenshot to analyze", type=["png", "jpg", "jpeg", "webp"])
            if uploaded_file is not None:
                safe_name = Path(uploaded_file.name).name
                save_dest = Path(app_cfg.get("screenshot_dir", str(config.detect_default_screenshot_dir()))) / safe_name
                with open(save_dest, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                st.success(f"Saved! Processing...")
                process_screenshot(str(save_dest))
                st.rerun()

# 7. Greeting Subheading Banner
col_greet, col_today = st.columns([8, 2])
with col_greet:
    st.markdown(f"""
    <div class="greeting-kicker">
        <span class="greeting-dot"></span>
        YOUR PERSONAL MEMORY, ORGANIZED
    </div>
    <div class="greeting-title">
        {greeting_prefix}, {user_name} <span class="greeting-star">✳</span>
    </div>
    <div class="greeting-subtitle">
        Here's what matters today. The rest can wait.
    </div>
    """, unsafe_allow_html=True)

with col_today:
    st.markdown(f"""
    <div style="text-align: right; margin-top: 10px;">
        <div class="today-badge-card">
            <div class="today-circle">G</div>
            <div style="text-align: left;">
                <div style="font-size: 9px; font-weight: 700; color: #a1a1aa; letter-spacing: 0.05em;">TODAY</div>
                <div style="font-size: 12px; font-weight: 700; color: #18181b;">{today_formatted}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# 8. Live Auto-Updating Workspace View Fragment
@st.fragment(run_every="4s")
def render_active_view(search_term: str):
    # Fetch database metrics
    stats = db.get_stats()
    all_recs = db.get_all_screenshots(search_query=search_term)
    
    # Calculate counts
    open_tasks_count = 0
    deadlines_count = 0
    all_tasks = []
    
    for r in all_recs:
        if r.tasks_list:
            open_tasks_count += len(r.tasks_list)
            for t in r.tasks_list:
                all_tasks.append({"task": t, "rec": r})
        if r.dates_list:
            deadlines_count += len(r.dates_list)

    total_screens = stats.get("total", len(all_recs))
    review_count = sum(1 for r in all_recs if r.status == ProcessStatus.FAILED or r.category == Category.OTHER)

    # Display 4 Metric / KPI Cards
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Open tasks</span>
                <span class="kpi-icon-box kpi-icon-green">☑</span>
            </div>
            <div class="kpi-value-row">
                <span class="kpi-num">{open_tasks_count:02d}</span>
                <span class="kpi-subtext">from your screenshots</span>
            </div>
            <div class="kpi-footer-status">
                <span class="kpi-bar-green"></span>
                <span>{open_tasks_count} extracted</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_k2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Upcoming deadlines</span>
                <span class="kpi-icon-box kpi-icon-peach">⏱</span>
            </div>
            <div class="kpi-value-row">
                <span class="kpi-num">{deadlines_count:02d}</span>
                <span class="kpi-subtext">dates detected</span>
            </div>
            <div class="kpi-footer-status">
                <span class="kpi-dot-peach"></span>
                <span>from processed screenshots</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_k3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Captured this week</span>
                <span class="kpi-icon-box kpi-icon-purple">📸</span>
            </div>
            <div class="kpi-value-row">
                <span class="kpi-num">{total_screens:02d}</span>
                <span class="kpi-subtext">in your local stash</span>
            </div>
            <div class="kpi-footer-status">
                <span class="kpi-dot-purple"></span>
                <span>{sum(1 for r in all_recs if r.status == ProcessStatus.PROCESSED)} organized</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_k4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-header">
                <span class="kpi-label">Need your review</span>
                <span class="kpi-icon-box kpi-icon-lavender">✳</span>
            </div>
            <div class="kpi-value-row">
                <span class="kpi-num">{review_count:02d}</span>
                <span style="background:#f3e8ff; color:#7e22ce; font-size:10px; font-weight:600; padding:2px 8px; border-radius:4px;">Review</span>
            </div>
            <div class="kpi-footer-status">
                <span class="kpi-dot-purple"></span>
                <span>AI is unsure about {review_count} details</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.write("")

    current_view = st.session_state.active_view

    if current_view == "Overview":
        st.subheader("Recently organized")
        if not all_recs:
            st.info("No screenshots have been organized yet. Take a screenshot in the watched folder and ScreenStash will process it here.")
        else:
            for record in all_recs[:8]:
                category = html.escape(record.category)
                title = html.escape(record.title or record.file_name)
                summary = html.escape(record.summary or "No summary was extracted.")
                source = html.escape(record.file_path)
                with st.container(border=True):
                    left, right = st.columns([5, 1])
                    with left:
                        st.markdown(f"**{title}** · `{category}`")
                        st.caption(summary)
                        st.caption(f"Source: {source}")
                    with right:
                        st.caption(record.status.value)
                        if record.file_path:
                            st.markdown(f"[Open original](file:///{source.replace(chr(92), '/')})")
                    if record.tasks_list:
                        st.write("Tasks: " + "; ".join(record.tasks_list))
        st.divider()

    # ---------------- VIEW 1: OVERVIEW ----------------
    if False and current_view == "Overview":
        col_mid_left, col_mid_right = st.columns([1, 1])

        # Left Column: Deadline Calendar
        with col_mid_left:
            st.markdown("""
            <div class="section-card">
                <div class="section-tag">KEEP THE IMPORTANT DATES</div>
                <div class="section-title-row">
                    <div class="section-title">Deadline calendar</div>
                    <div style="font-size: 11px; color: #71717a; display: flex; gap: 8px;">
                        <span><span style="color:#ef4444">●</span> Deadline</span>
                        <span><span style="color:#10b981">●</span> Event</span>
                        <span><span style="color:#a855f7">●</span> Needs review</span>
                    </div>
                </div>
                
                <div style="display: flex; justify-content: flex-end; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; margin-bottom: 8px;">
                    <span style="cursor:pointer; color:#a1a1aa;">&larr;</span>
                    <span>October 2026</span>
                    <span style="cursor:pointer; color:#a1a1aa;">&rarr;</span>
                </div>

                <table class="cal-table">
                    <thead>
                        <tr>
                            <th class="cal-th">M</th><th class="cal-th">T</th><th class="cal-th">W</th>
                            <th class="cal-th">T</th><th class="cal-th">F</th><th class="cal-th">S</th><th class="cal-th">S</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td class="cal-td muted">28</td><td class="cal-td muted">29</td><td class="cal-td muted">30</td>
                            <td class="cal-td">1</td><td class="cal-td">2</td><td class="cal-td">3</td><td class="cal-td">4</td>
                        </tr>
                        <tr>
                            <td class="cal-td">5</td><td class="cal-td">6</td><td class="cal-td">7</td>
                            <td class="cal-td">8</td><td class="cal-td">9</td><td class="cal-td">10</td><td class="cal-td">11</td>
                        </tr>
                        <tr>
                            <td class="cal-td">12</td><td class="cal-td">13</td><td class="cal-td">14</td>
                            <td class="cal-td">15</td><td class="cal-td">16</td><td class="cal-td">17</td><td class="cal-td">18</td>
                        </tr>
                        <tr>
                            <td class="cal-td">19</td><td class="cal-td">20</td><td class="cal-td">21</td>
                            <td class="cal-td today-box">22</td>
                            <td class="cal-td today-box" style="border: 1.5px solid #84cc16;">
                                23
                                <span class="cal-dot cal-dot-deadline"></span>
                            </td>
                            <td class="cal-td">24 <span class="cal-dot cal-dot-deadline"></span></td>
                            <td class="cal-td">25 <span class="cal-dot cal-dot-event"></span></td>
                        </tr>
                        <tr>
                            <td class="cal-td">26</td><td class="cal-td">27 <span class="cal-dot cal-dot-event"></span></td>
                            <td class="cal-td">28</td><td class="cal-td">29 <span class="cal-dot cal-dot-deadline"></span></td>
                            <td class="cal-td">30</td><td class="cal-td">31</td><td class="cal-td muted">1</td>
                        </tr>
                    </tbody>
                </table>

                <div class="next-deadline-banner">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <div style="width: 28px; height: 28px; border-radius: 6px; background: #dcfce7; color: #166534; display: flex; align-items: center; justify-content: center; font-weight: 700;">L</div>
                        <div>
                            <div style="font-size: 10px; font-weight: 700; color: #15803d; text-transform: uppercase;">FRIDAY, OCTOBER 23</div>
                            <div class="deadline-title">Send final presentation slides</div>
                            <div class="deadline-meta">Deadline detected from screenshot</div>
                        </div>
                    </div>
                    <div style="font-size: 11px; font-weight: 600; color: #166534; cursor: pointer;">Next deadline ↗</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Right Column: Up Next Task Card
        with col_mid_right:
            st.markdown("""
            <div class="section-card">
                <div class="section-tag">MAKE IT COUNT</div>
                <div class="section-title-row">
                    <div class="section-title">Up next</div>
                    <div class="section-link">All tasks ↗</div>
                </div>

                <!-- Highlighted Top Priority Card -->
                <div class="up-next-task">
                    <div class="date-chip-peach">
                        <span class="date-chip-num">24</span>
                        <span class="date-chip-month">OCT</span>
                    </div>
                    <div style="flex-grow: 1;">
                        <div style="display: flex; gap: 6px; align-items: center; margin-bottom: 4px;">
                            <span class="badge-peach-pill">Due in 2 days</span>
                            <span style="font-size: 10px; color: #a1a1aa;">• 94% confidence</span>
                        </div>
                        <div style="font-size: 14px; font-weight: 700; color: #18181b;">Submit project proposal</div>
                        <div style="font-size: 12px; color: #71717a; margin-top: 2px;">Finish the proposal and send it to the course portal</div>
                        <div class="source-chip">
                            <span>📄 From: assignment-brief.png</span>
                            <span style="color: #4f46e5; font-weight: 600; margin-left: 6px;">↗ Evidence</span>
                        </div>
                    </div>
                </div>

                <!-- Secondary Checklist -->
                <div class="action-item-row">
                    <div class="action-item-left">
                        <input type="checkbox" style="cursor: pointer; width: 16px; height: 16px;">
                        <div>
                            <div class="action-item-title">Send final presentation slides</div>
                            <div class="action-item-sub">Tomorrow • from a chat screenshot</div>
                        </div>
                    </div>
                    <div style="font-size: 12px; color: #a1a1aa; cursor: pointer;">✏️</div>
                </div>

                <div class="action-item-row">
                    <div class="action-item-left">
                        <input type="checkbox" style="cursor: pointer; width: 16px; height: 16px;">
                        <div>
                            <div class="action-item-title">Book a project check-in</div>
                            <div class="action-item-sub">Oct 27 • date needs confirmation</div>
                        </div>
                    </div>
                    <div style="font-size: 11px; background: #faf5ff; color: #7e22ce; padding: 2px 6px; border-radius: 4px; font-weight: 700;">!</div>
                </div>

                <div style="border: 1px dashed #d4d4d8; border-radius: 10px; padding: 10px; text-align: center; color: #71717a; font-size: 12px; font-weight: 600; cursor: pointer; margin-top: 10px;">
                    + Add a task
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Bottom Two-Column Row: Recently Organized & Evidence Trail
        col_bot_left, col_bot_right = st.columns([1, 1])

        # Bottom Left: Recently Organized
        with col_bot_left:
            st.markdown("""
            <div class="section-card">
                <div class="section-tag">FRESH FROM YOUR SCREEN</div>
                <div class="section-title-row">
                    <div class="section-title">Recently organized</div>
                    <div class="section-link">View all ↗</div>
                </div>

                <div class="organized-row">
                    <div class="organized-left">
                        <div class="thumb-pill thumb-lavender">Project<br>Brief</div>
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-size: 13px; font-weight: 700;">Submit project proposal</span>
                                <span style="background:#eff6ff; color:#1d4ed8; font-size:10px; font-weight:600; padding:1px 6px; border-radius:4px;">Task</span>
                            </div>
                            <div style="font-size: 11px; color: #71717a; margin-top:2px;">Deadline detected - Oct 24 • High confidence • 2m ago</div>
                        </div>
                    </div>
                    <div style="color: #a1a1aa; font-size: 12px; cursor: pointer;">✏️</div>
                </div>

                <div class="organized-row">
                    <div class="organized-left">
                        <div class="thumb-pill thumb-peach">Design<br>Market</div>
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-size: 13px; font-weight: 700;">Sunday design market</span>
                                <span style="background:#ffedd5; color:#c2410c; font-size:10px; font-weight:600; padding:1px 6px; border-radius:4px;">Event</span>
                            </div>
                            <div style="font-size: 11px; color: #71717a; margin-top:2px;">Time & place extracted - Oct 25 • High confidence • 14m ago</div>
                        </div>
                    </div>
                    <div style="color: #a1a1aa; font-size: 12px; cursor: pointer;">✏️</div>
                </div>

                <div class="organized-row">
                    <div class="organized-left">
                        <div class="thumb-pill thumb-green">Check-In<br>Chat</div>
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span style="font-size: 13px; font-weight: 700;">Project check-in</span>
                                <span style="background:#faf5ff; color:#7e22ce; font-size:10px; font-weight:600; padding:1px 6px; border-radius:4px;">Review</span>
                            </div>
                            <div style="font-size: 11px; color: #71717a; margin-top:2px;">Proposed date - Oct 27 • Confirm date • 22m ago</div>
                        </div>
                    </div>
                    <div style="font-size: 11px; background: #faf5ff; color: #7e22ce; padding: 2px 6px; border-radius: 4px; font-weight: 700;">!</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Bottom Right: Evidence Trail
        with col_bot_right:
            st.markdown("""
            <div class="section-card">
                <div class="section-tag">DON'T LOSE THE WHY</div>
                <div class="section-title-row">
                    <div class="section-title">Evidence trail</div>
                    <div style="background:#fafaf9; border:1px solid #ebe9e1; border-radius:6px; font-size:11px; padding:3px 8px; color:#71717a;">
                        Every decision has a source
                    </div>
                </div>
                <div style="font-size: 12px; color: #71717a; margin-bottom: 14px;">
                    Hover or focus any item to inspect the original screenshot and the exact text that supports it.
                </div>

                <div class="organized-row">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:22px; height:22px; border-radius:50%; background:#dcfce7; color:#15803d; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;">✓</div>
                        <div>
                            <div style="font-size: 12px; font-weight: 700;">"Submit project proposal"</div>
                            <div style="font-size: 11px; color: #71717a;">Decision: task • Due date: Oct 24</div>
                        </div>
                    </div>
                    <div class="evidence-quote-box">"Submit by October 24"</div>
                </div>

                <div class="organized-row">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:22px; height:22px; border-radius:50%; background:#ffedd5; color:#c2410c; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;">+</div>
                        <div>
                            <div style="font-size: 12px; font-weight: 700;">"Sunday design market"</div>
                            <div style="font-size: 11px; color: #71717a;">Decision: event • Place: Riverside</div>
                        </div>
                    </div>
                    <div class="evidence-quote-box">"Sunday • 10 AM • Riverside"</div>
                </div>

                <div class="organized-row">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:22px; height:22px; border-radius:50%; background:#faf5ff; color:#7e22ce; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;">!</div>
                        <div>
                            <div style="font-size: 12px; font-weight: 700;">"Project check-in"</div>
                            <div style="font-size: 11px; color: #71717a;">Decision: suggested task • Date uncertain</div>
                        </div>
                    </div>
                    <div class="evidence-quote-box">"next Tuesday" &rarr; verify</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ---------------- VIEW 2: TASKS ----------------
    elif current_view == "Tasks":
        st.markdown("""
        <div class="section-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div>
                    <div class="section-tag">YOUR ACTION LIST</div>
                    <div class="section-title">Tasks & deadlines</div>
                </div>
                <div style="background: #18181b; color: #ffffff; padding: 8px 16px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer;">
                    + Add task
                </div>
            </div>
        """, unsafe_allow_html=True)

        if not all_tasks:
            st.info("No tasks have been extracted from your screenshots yet.")
        for index, item in enumerate(all_tasks):
            title = item["task"]
            source_record = item["rec"]
            col_t_check, col_t_btn = st.columns([8, 2])
            with col_t_check:
                st.checkbox(
                    f"**{title}** — *{source_record.created_at[:10]}*",
                    key=f"task_chk_view_{source_record.id}_{index}",
                )
            with col_t_btn:
                with st.popover("View evidence ↗"):
                    st.caption(f"Source file: `{source_record.file_name}`")
                    st.info(source_record.raw_ocr_text[:500] or source_record.summary)

        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- VIEW 3: CALENDAR ----------------
    elif current_view == "Calendar":
        st.markdown("""
        <div class="section-card">
            <div class="section-tag">PLAN AHEAD</div>
            <div class="section-title-row">
                <div class="section-title">Calendar & deadlines</div>
                <div style="display: flex; gap: 8px; font-size: 12px; font-weight: 600;">
                    <span style="cursor:pointer; color:#a1a1aa;">&larr;</span>
                    <span>October 2026</span>
                    <span style="cursor:pointer; color:#a1a1aa;">&rarr;</span>
                </div>
            </div>

            <table class="cal-table" style="font-size: 14px;">
                <thead>
                    <tr>
                        <th class="cal-th">M</th><th class="cal-th">T</th><th class="cal-th">W</th>
                        <th class="cal-th">T</th><th class="cal-th">F</th><th class="cal-th">S</th><th class="cal-th">S</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="cal-td muted">28</td><td class="cal-td muted">29</td><td class="cal-td muted">30</td>
                        <td class="cal-td">1</td><td class="cal-td">2</td><td class="cal-td">3</td><td class="cal-td">4</td>
                    </tr>
                    <tr>
                        <td class="cal-td">5</td><td class="cal-td">6</td><td class="cal-td">7</td>
                        <td class="cal-td">8</td><td class="cal-td">9</td><td class="cal-td">10</td><td class="cal-td">11</td>
                    </tr>
                    <tr>
                        <td class="cal-td">12</td><td class="cal-td">13</td><td class="cal-td">14</td>
                        <td class="cal-td">15</td><td class="cal-td">16</td><td class="cal-td">17</td><td class="cal-td">18</td>
                    </tr>
                    <tr>
                        <td class="cal-td">19</td><td class="cal-td">20</td><td class="cal-td">21</td>
                        <td class="cal-td today-box">22</td>
                        <td class="cal-td today-box">23 <span class="cal-dot cal-dot-deadline"></span></td>
                        <td class="cal-td">24 <span class="cal-dot cal-dot-deadline"></span></td>
                        <td class="cal-td">25 <span class="cal-dot cal-dot-event"></span></td>
                    </tr>
                    <tr>
                        <td class="cal-td">26</td><td class="cal-td">27 <span class="cal-dot cal-dot-event"></span></td>
                        <td class="cal-td">28</td><td class="cal-td">29 <span class="cal-dot cal-dot-deadline"></span></td>
                        <td class="cal-td">30</td><td class="cal-td">31</td><td class="cal-td muted">1</td>
                    </tr>
                </tbody>
            </table>

            <div class="next-deadline-banner" style="margin-top: 20px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 28px; height: 28px; border-radius: 6px; background: #dcfce7; color: #166534; display: flex; align-items: center; justify-content: center; font-weight: 700;">L</div>
                    <div>
                        <div style="font-size: 10px; font-weight: 700; color: #15803d; text-transform: uppercase;">FRIDAY, OCTOBER 23</div>
                        <div class="deadline-title">Send final presentation slides</div>
                        <div class="deadline-meta">Source-linked event or deadline</div>
                    </div>
                </div>
                <div style="font-size: 12px; font-weight: 600; color: #166534; cursor: pointer;">Next deadline ↗</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------- VIEW 4: REFERENCES ----------------
    elif current_view == "References":
        st.markdown("""
        <div class="section-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div>
                    <div class="section-tag">SOURCE-FIRST MEMORY</div>
                    <div class="section-title">Saved references</div>
                </div>
                <div style="font-size: 12px; color: #71717a; font-weight: 600; cursor: pointer;">
                    + Import screenshot
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_ref1, col_ref2 = st.columns(2)
        with col_ref1:
            st.markdown("""
            <div style="background:#ffffff; border:1px solid #e8e6df; border-radius:12px; overflow:hidden; margin-bottom:16px;">
                <div style="background:#f3e8ff; padding:30px 20px; text-align:center;">
                    <div style="font-size:10px; font-weight:700; color:#7e22ce; text-transform:uppercase;">SAMPLE PREVIEW</div>
                    <div style="font-size:16px; font-weight:700; color:#581c87; margin-top:4px;">Color palette inspiration</div>
                    <div style="font-size:10px; color:#7e22ce; margin-top:2px;">COLOR-STUDY.PNG</div>
                </div>
                <div style="padding:14px; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-size:13px; font-weight:700;">Color palette inspiration</div>
                        <div style="font-size:11px; color:#71717a;">Reference • 4 colors extracted</div>
                    </div>
                    <div style="font-size:11px; color:#4f46e5; font-weight:600; cursor:pointer;">Open evidence ↗</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with col_ref2:
            st.markdown("""
            <div style="background:#ffffff; border:1px solid #e8e6df; border-radius:12px; overflow:hidden; margin-bottom:16px;">
                <div style="background:#fef3c7; padding:30px 20px; text-align:center;">
                    <div style="font-size:10px; font-weight:700; color:#b45309; text-transform:uppercase;">RECIPE ARCHIVE</div>
                    <div style="font-size:16px; font-weight:700; color:#78350f; margin-top:4px;">Slow Sunday pasta</div>
                    <div style="font-size:10px; color:#b45309; margin-top:2px;">PASTA-RECIPE.PNG</div>
                </div>
                <div style="padding:14px; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-size:13px; font-weight:700;">Slow Sunday pasta</div>
                        <div style="font-size:11px; color:#71717a;">Reference • Saved as recipe</div>
                    </div>
                    <div style="font-size:11px; color:#4f46e5; font-weight:600; cursor:pointer;">Open evidence ↗</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- VIEW 5: ALL SCREENSHOTS ----------------
    elif current_view == "All screenshots":
        st.markdown("""
        <div class="section-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div>
                    <div class="section-tag">SOURCE-FIRST MEMORY</div>
                    <div class="section-title">Screenshot library</div>
                </div>
                <div style="font-size: 12px; color: #71717a; font-weight: 600; cursor: pointer;">
                    + Import screenshot
                </div>
            </div>
        """, unsafe_allow_html=True)

        cols_grid = st.columns(3)
        colors = ["#dcfce7", "#ffedd5", "#f3e8ff", "#fef3c7", "#eff6ff"]
        text_colors = ["#15803d", "#c2410c", "#7e22ce", "#b45309", "#1d4ed8"]

        for idx, rec in enumerate(all_recs[:9]):
            c = cols_grid[idx % 3]
            bg_color = colors[idx % len(colors)]
            fg_color = text_colors[idx % len(text_colors)]

            with c:
                st.markdown(f"""
                <div style="background:#ffffff; border:1px solid #e8e6df; border-radius:12px; overflow:hidden; margin-bottom:16px;">
                    <div style="background:{bg_color}; padding:24px 16px; text-align:center;">
                        <div style="font-size:9px; font-weight:700; color:{fg_color}; text-transform:uppercase;">SAMPLE PREVIEW</div>
                        <div style="font-size:14px; font-weight:700; color:{fg_color}; margin-top:4px;">{rec.title[:26]}</div>
                        <div style="font-size:10px; color:{fg_color}; margin-top:2px;">{rec.file_name}</div>
                    </div>
                    <div style="padding:12px 14px; display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div style="font-size:12px; font-weight:700;">{rec.title[:24]}</div>
                            <div style="font-size:10px; color:#71717a;">{rec.category} • {rec.created_at[:10]}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                with st.popover(f"Open evidence #{rec.id} ↗"):
                    img_path = Path(rec.file_path)
                    if img_path.exists():
                        try:
                            st.image(Image.open(img_path), use_container_width=True)
                        except Exception:
                            st.caption("Preview unavailable")
                    st.markdown(f"**Classification:** `{rec.category}`")
                    st.markdown(f"**Summary:** {rec.summary or '(No summary)'}")
                    if rec.tasks_list:
                        st.markdown(f"**Tasks:** {', '.join(rec.tasks_list)}")
                    if rec.dates_list:
                        st.markdown(f"**Dates:** {', '.join(rec.dates_list)}")
                    if rec.raw_ocr_text:
                        with st.expander("Raw Extracted OCR Text"):
                            st.text(rec.raw_ocr_text[:600])

        st.markdown("</div>", unsafe_allow_html=True)

    # 9. Concept Preview Footer
    st.markdown("""
    <div class="workspace-footer">
        <div><span style="color:#84cc16;">●</span> ScreenStash concept preview</div>
        <div>Original screenshot &rarr; extracted details &rarr; explainable decision</div>
        <div style="cursor:pointer; color:#71717a;">Product overview ↗</div>
    </div>
    """, unsafe_allow_html=True)


# Render the active workspace view
render_active_view(search_query)
