"""
Streamlit Dashboard for ScreenStash.
Provides a premium desktop interface for browsing, searching, editing,
and managing AI-extracted screenshot insights and tasks.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
from PIL import Image

import config
import database as db
from models import Category, ProcessStatus, ScreenshotRecord
from processor import process_screenshot
from watcher import ScreenshotWatcher, scan_existing_screenshots
from background_service import is_daemon_running, stop_running_daemon
import subprocess

# Configure Streamlit page
st.set_page_config(
    page_title="ScreenStash — Screenshot-to-Plan",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics, dark mode cards, badges, and modern typography
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Native Desktop Mode: Hide Streamlit Web Chrome, Menus & Headers */
    #MainMenu { visibility: hidden !important; display: none !important; }
    header[data-testid="stHeader"] { visibility: hidden !important; height: 0 !important; }
    footer { visibility: hidden !important; display: none !important; }
    div[data-testid="stDecoration"] { display: none !important; }
    div[data-testid="stStatusWidget"] { display: none !important; }
    .stDeployButton, [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding-top: 1.2rem !important; }
    
    /* Header Gradient */
    .app-header {
        background: linear-gradient(135deg, #1e1e2f 0%, #11111b 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px 30px;
        margin-bottom: 24px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    }
    
    .app-title {
        font-size: 28px;
        font-weight: 700;
        background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
    }
    
    .app-subtitle {
        color: #94a3b8;
        font-size: 14px;
        margin: 0;
    }
    
    /* Stat Cards */
    .stat-card {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 12px;
        padding: 16px 20px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .stat-card:hover {
        border-color: rgba(96, 165, 250, 0.4);
        transform: translateY(-2px);
    }
    .stat-num {
        font-size: 26px;
        font-weight: 700;
        color: #f8fafc;
    }
    .stat-label {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-top: 4px;
    }
    
    /* Category Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.02em;
        margin-bottom: 8px;
    }
    .badge-task { background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.4); }
    .badge-event { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; border: 1px solid rgba(168, 85, 247, 0.4); }
    .badge-receipt { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-reference { background: rgba(245, 158, 11, 0.2); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-other { background: rgba(148, 163, 184, 0.2); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.4); }
    
    /* Status Pills */
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        padding: 3px 8px;
        border-radius: 6px;
    }
    .dot-green { width: 8px; height: 8px; border-radius: 50%; background: #10b981; }
    .dot-amber { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; }
    .dot-red { width: 8px; height: 8px; border-radius: 50%; background: #ef4444; }

    /* Screenshot Card */
    .screenshot-card {
        background: #181825;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 20px;
        transition: all 0.2s ease;
    }
    .screenshot-card:hover {
        border-color: rgba(147, 197, 253, 0.3);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    
    .card-title {
        font-size: 18px;
        font-weight: 600;
        color: #f1f5f9;
        margin-top: 4px;
        margin-bottom: 8px;
    }
    
    .card-summary {
        font-size: 14px;
        color: #cbd5e1;
        line-height: 1.5;
        margin-bottom: 12px;
    }
    
    .tag-chip {
        display: inline-block;
        background: rgba(255, 255, 255, 0.06);
        color: #94a3b8;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    
    .task-item {
        background: rgba(255, 255, 255, 0.03);
        border-left: 3px solid #60a5fa;
        padding: 6px 10px;
        margin-bottom: 6px;
        border-radius: 0 6px 6px 0;
        font-size: 13px;
        color: #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)


# Initialize DB on load
db.init_db()
app_cfg = config.load_config()


# Background watcher lifecycle: Only run in-app watcher if the background daemon is NOT running
if is_daemon_running():
    if "watcher_instance" in st.session_state and st.session_state.watcher_instance:
        try:
            st.session_state.watcher_instance.stop()
        except Exception:
            pass
        st.session_state.watcher_instance = None
else:
    if "watcher_instance" not in st.session_state or st.session_state.watcher_instance is None:
        try:
            watcher = ScreenshotWatcher()
            watcher.start()
            st.session_state.watcher_instance = watcher
        except Exception as e:
            st.session_state.watcher_instance = None


def test_ollama_status(url: str) -> bool:
    """Check if local Ollama server is reachable."""
    try:
        res = requests.get(f"{url.rstrip('/')}/api/tags", timeout=1.5)
        return res.status_code == 200
    except Exception:
        return False


def test_tesseract_status(cmd_path: str) -> bool:
    """Check if Tesseract binary exists or is on PATH."""
    if os.path.exists(cmd_path):
        return True
    import shutil
    return shutil.which("tesseract") is not None


# ---------------- SIDEBAR: NAVIGATION & SETTINGS ----------------
with st.sidebar:
    st.markdown("### ⚙️ System Status")
    
    daemon_active = is_daemon_running()
    ollama_ok = test_ollama_status(app_cfg.get("ollama_url", "http://localhost:11434"))
    tesseract_ok = test_tesseract_status(app_cfg.get("tesseract_cmd", ""))

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if daemon_active:
            st.markdown('<div class="status-pill"><span class="dot-green"></span> Daemon On</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-pill"><span class="dot-amber"></span> Daemon Idle</div>', unsafe_allow_html=True)
    with col_s2:
        if ollama_ok:
            st.markdown('<div class="status-pill"><span class="dot-green"></span> Ollama AI</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-pill"><span class="dot-amber"></span> Local NLP</div>', unsafe_allow_html=True)

    # Daemon toggle button
    if daemon_active:
        if st.button("⏹️ Stop Background Daemon", use_container_width=True):
            stop_running_daemon()
            st.rerun()
    else:
        if st.button("▶️ Start Background Daemon", use_container_width=True):
            pythonw = Path(sys.executable).parent / "pythonw.exe"
            exe = str(pythonw) if pythonw.exists() else sys.executable
            target = str(Path(__file__).parent / "background.pyw")
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([exe, target], cwd=str(Path(__file__).parent), creationflags=flags, close_fds=True)
            time.sleep(0.5)
            st.rerun()

    st.markdown("---")
    st.markdown("### 📁 Monitored Folder")
    folder_path = app_cfg.get("screenshot_dir", "")
    st.caption(f"`{folder_path}`")
    
    if st.button("🔄 Sync / Scan Folder Now", use_container_width=True):
        with st.spinner("Scanning screenshot directory..."):
            count = scan_existing_screenshots(folder_path)
            st.success(f"Scanned directory! {count} items synced.")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    st.markdown("### 🛠️ Settings & AI Model")
    with st.expander("Configure Endpoints"):
        new_screenshot_dir = st.text_input("Screenshot Directory", value=folder_path)
        new_ollama_url = st.text_input("Ollama Endpoint", value=app_cfg.get("ollama_url", "http://localhost:11434"))
        new_ollama_model = st.text_input("Ollama Model", value=app_cfg.get("ollama_model", "llama3:latest"))
        new_tesseract_cmd = st.text_input("Tesseract Binary Path", value=app_cfg.get("tesseract_cmd", ""))

        if st.button("Save Settings", key="save_settings_btn"):
            app_cfg["screenshot_dir"] = new_screenshot_dir
            app_cfg["ollama_url"] = new_ollama_url
            app_cfg["ollama_model"] = new_ollama_model
            app_cfg["tesseract_cmd"] = new_tesseract_cmd
            config.save_config(app_cfg)
            st.success("Settings saved successfully!")
            time.sleep(1)
            st.rerun()

    with st.expander("Privacy & Local Guarantee"):
        st.info(
            "🔒 **100% Local & Private**\n\n"
            "• Screenshots remain in your local screenshot folder.\n"
            "• OCR and classification run on your CPU/GPU.\n"
            "• Database is stored locally at:\n"
            f"`{config.DATABASE_PATH}`"
        )


# ---------------- MAIN CONTENT AREA ----------------

# Top Header banner
st.markdown("""
<div class="app-header">
    <div class="app-title">📸 ScreenStash — Screenshot-to-Plan</div>
    <div class="app-subtitle">Turn raw desktop captures into actionable tasks, calendar events, receipts, and organized notes.</div>
</div>
""", unsafe_allow_html=True)

# Search & Filter Controls
col_f1, col_f2, col_f3 = st.columns([3, 1.5, 1.5])
with col_f1:
    search_query = st.text_input("🔍 Search screenshots, text, tasks, tags...", placeholder="Type to search...", label_visibility="collapsed")
with col_f2:
    category_filter = st.selectbox(
        "Category",
        options=["All", "Task", "Event", "Receipt", "Reference", "Other"],
        label_visibility="collapsed"
    )
with col_f3:
    status_filter = st.selectbox(
        "Status",
        options=["All", "PROCESSED", "PENDING", "FAILED"],
        label_visibility="collapsed"
    )

st.write("")


@st.fragment(run_every="4s")
def render_live_feed(search_q: str, cat_filter: str, stat_filter: str):
    # Dynamic Key Metrics Row
    stats = db.get_stats()
    cat_counts = stats.get("categories", {})

    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-num">{stats.get('total', 0)}</div>
            <div class="stat-label">Total Screens</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-num">{cat_counts.get('Task', 0)}</div>
            <div class="stat-label">Tasks & To-Dos</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-num">{cat_counts.get('Event', 0)}</div>
            <div class="stat-label">Events & Dates</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-num">{cat_counts.get('Receipt', 0)}</div>
            <div class="stat-label">Receipts Logged</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m5:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-num">{cat_counts.get('Reference', 0)}</div>
            <div class="stat-label">References</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    # Fetch filtered items
    records = db.get_all_screenshots(
        category=cat_filter,
        status=stat_filter,
        search_query=search_q
    )

    if not records:
        st.info("No screenshots found matching your filters. Take a screenshot (`Win+Shift+S` or `Win+PrtScn`) to test the 'ScreenStash Saved' popup!")
        return

    for rec in records:
        category_cls = f"badge-{rec.category.lower()}"
        
        with st.container():
            col_img, col_info, col_actions = st.columns([1.5, 3.5, 1.5])
            
            with col_img:
                img_path = Path(rec.file_path)
                if img_path.exists():
                    try:
                        thumb = Image.open(img_path)
                        st.image(thumb, use_container_width=True)
                    except Exception:
                        st.text("🖼️ Image preview unavailable")
                else:
                    st.warning(f"File moved: {rec.file_name}")
                st.caption(f"`{rec.created_at[:16]}`")

            with col_info:
                st.markdown(f'<span class="badge {category_cls}">{rec.category}</span>', unsafe_allow_html=True)
                st.markdown(f"<div class='card-title'>{rec.title}</div>", unsafe_allow_html=True)
                
                if rec.summary:
                    st.markdown(f"<div class='card-summary'>{rec.summary}</div>", unsafe_allow_html=True)

                # Tasks display
                tasks = rec.tasks_list
                if tasks:
                    st.markdown("**Tasks & Action Items:**")
                    for t in tasks:
                        st.markdown(f'<div class="task-item">☐ {t}</div>', unsafe_allow_html=True)

                # Dates display
                dates = rec.dates_list
                if dates:
                    st.markdown(f"🗓️ **Dates / Deadlines:** {', '.join(dates)}")

                # Amount for receipts
                if rec.amount:
                    st.markdown(f"💳 **Amount:** `{rec.amount}`")

                # Tags display
                tags = rec.tags_list
                if tags:
                    tag_html = "".join([f'<span class="tag-chip">#{t}</span>' for t in tags])
                    st.markdown(tag_html, unsafe_allow_html=True)

            with col_actions:
                st.write("")
                # Edit modal / expander
                with st.popover("✏️ Edit Details"):
                    st.markdown(f"**Edit Record #{rec.id}**")
                    new_title = st.text_input("Title", value=rec.title, key=f"title_{rec.id}")
                    new_cat = st.selectbox(
                        "Category",
                        options=[c.value for c in Category],
                        index=[c.value for c in Category].index(rec.category) if rec.category in [c.value for c in Category] else 0,
                        key=f"cat_{rec.id}"
                    )
                    new_summary = st.text_area("Summary", value=rec.summary, key=f"sum_{rec.id}")
                    new_tasks_text = st.text_area("Tasks (one per line)", value="\n".join(rec.tasks_list), key=f"tasks_{rec.id}")
                    new_dates_text = st.text_input("Dates (comma separated)", value=", ".join(rec.dates_list), key=f"dates_{rec.id}")
                    new_amount = st.text_input("Amount", value=rec.amount or "", key=f"amt_{rec.id}")
                    new_tags_text = st.text_input("Tags (comma separated)", value=", ".join(rec.tags_list), key=f"tags_{rec.id}")

                    if st.button("Save Changes", key=f"save_btn_{rec.id}"):
                        parsed_tasks = [t.strip() for t in new_tasks_text.splitlines() if t.strip()]
                        parsed_dates = [d.strip() for d in new_dates_text.split(",") if d.strip()]
                        parsed_tags = [tg.strip() for tg in new_tags_text.split(",") if tg.strip()]
                        db.update_user_edits(
                            rec.id,
                            title=new_title,
                            category=new_cat,
                            summary=new_summary,
                            tasks=parsed_tasks,
                            dates=parsed_dates,
                            tags=parsed_tags,
                            amount=new_amount if new_amount else None
                        )
                        st.success("Updated!")
                        time.sleep(0.5)
                        st.rerun()

                # Re-process button
                if st.button("⚡ Re-analyze", key=f"reproc_{rec.id}", use_container_width=True):
                    with st.spinner("Re-analyzing image..."):
                        process_screenshot(rec.file_path)
                        st.success("Re-analyzed!")
                        time.sleep(0.5)
                        st.rerun()

                # View OCR Raw Text
                with st.popover("📄 Raw OCR"):
                    st.text_area("Extracted OCR Text", value=rec.raw_ocr_text or "(No OCR text)", height=200, key=f"ocr_{rec.id}")

                # Delete button
                if st.button("🗑️ Delete", key=f"del_{rec.id}", use_container_width=True):
                    db.delete_screenshot(rec.id)
                    st.rerun()

            st.markdown("<hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.06); margin: 15px 0;'>", unsafe_allow_html=True)


# Render the auto-updating live feed
render_live_feed(search_query, category_filter, status_filter)
