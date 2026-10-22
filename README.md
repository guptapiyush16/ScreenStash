# 📸 ScreenStash — Screenshot-to-Plan Desktop MVP

> **Turn raw desktop screenshots into actionable tasks, calendar events, receipts, and organized knowledge automatically.**

ScreenStash is a local-first desktop application that runs silently in the background, detects whenever you take a screenshot, extracts its text using OCR, interprets and categorizes the information with local AI, and presents everything in an interactive desktop dashboard.

---

## ✨ Features

- ⚡ **Automatic Detection**: Monitors your operating system's default screenshot folder (`Win+PrtScn`, `Win+Shift+S`, Snipping Tool) with sub-second debounce protection.
- 🔍 **Local OCR & AI Pipeline**: Extracts text via Tesseract OCR and structures insights using local open-weight models via **Ollama** (`llama3`, `mistral`, `phi3`).
- 🛡️ **Zero-Crash Heuristic Fallback**: Includes an intelligent offline regex/linguistic engine that extracts to-do checklists, dates, receipts, and categories even if Ollama or Tesseract are not installed yet.
- 🔒 **100% Private & Local-First**: No cloud accounts, external databases, or network telemetry. Your images and extracted data never leave your computer.
- 🗄️ **Clean OS App Data Separation**: Database (`screenstash.db`), logs (`screenstash.log`), and settings are stored in `%LOCALAPPDATA%\ScreenStash` (Windows) or `~/.local/share/ScreenStash` (Linux/macOS), keeping your code repo pristine.
- 📊 **Rich Streamlit Desktop UI**: Dark-mode dashboard with category badges, instant search, to-do checklists, in-place editing, manual screenshot drag-and-drop, and on-demand folder sync.
- 🚀 **One-Click Desktop Launch**: Double-click `run_desktop.bat` or run `python run_desktop.py` to start the watcher and dashboard simultaneously.

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.10+ | Core processing pipeline & application logic |
| **Filesystem Watcher** | Watchdog | Cross-platform directory event monitoring with debouncing |
| **OCR Engine** | Tesseract (pytesseract) | High-accuracy local optical character recognition |
| **Local AI Engine** | Ollama (`llama3:latest`) | Open-weight model for structured JSON parsing |
| **Fallback AI** | Pure Python NLP / Regex | Resilient offline extraction of dates, amounts, and tasks |
| **Database** | SQLite3 | Fast, embedded, local-first indexed storage |
| **Desktop UI** | Streamlit | Modern dashboard with instant search, metrics, and edit popovers |

---

## 📁 Project Structure

```
ScreenStash/
├── app.py                 # Streamlit desktop dashboard
├── watcher.py             # Watchdog observer & directory scanning
├── processor.py           # Stabilization, hashing, OCR, and AI pipeline
├── database.py            # SQLite schema, indexing, and CRUD operations
├── models.py              # Pydantic schemas and dataclasses
├── config.py              # OS application data directory & path auto-detection
├── run_desktop.py         # Unified desktop launcher (watcher + browser UI)
├── run_desktop.bat        # Windows one-click batch launcher
├── requirements.txt       # Dependencies
├── README.md              # Documentation
├── Decisions.mc           # Architectural decision records
├── Flow.md                # Execution travel and function flow map
├── tech.md                # Technical interview questions and answers
└── tests/
    └── test_pipeline.py   # Unit & integration test suite
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10 or newer installed
- (Optional, Recommended) [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) for Windows
- (Optional, Recommended) [Ollama](https://ollama.ai/) with your preferred model (`ollama pull llama3`)

> **Note**: Even if you do not have Tesseract or Ollama installed yet, ScreenStash will gracefully run using its built-in fallback engine!

### 2. 1-Click Installation & Setup

#### On Windows:
Double-click `install.bat` or run in terminal:
```bash
python setup_app.py
```
This automatically:
- Installs dependencies from `requirements.txt`
- Auto-detects your Windows screenshot folder (including OneDrive paths)
- Initializes the local SQLite database
- Creates a **Desktop shortcut** (`ScreenStash Dashboard.lnk`)
- Registers ScreenStash in **Windows Startup** (`shell:startup`) so it runs silently on boot
- Starts the silent background monitoring service (`background.pyw`) immediately!

#### On macOS / Linux:
```bash
pip install -r requirements.txt
python setup_app.py
```

### 3. Background Service & Live Popups

Once setup is complete, ScreenStash runs 24/7 in the background:
1. **Take a screenshot normally** anywhere on your PC (`Win+Shift+S` or `Win+PrtScn`).
2. A sleek dark-mode popup appears in the bottom-right corner:
   **`📸 ScreenStash Saved` — AI is organizing your screenshot...**
3. Once processed, it updates to:
   **`✓ Organized as Task`** (or `Event`, `Receipt`).
4. Click the popup at any time to open your organized dashboard!

### 4. CLI Control Center (`screenstash.py`)
```bash
python screenstash.py status      # Check if background service is running
python screenstash.py start       # Start background daemon
python screenstash.py stop        # Stop background daemon
python screenstash.py dashboard   # Open dashboard in browser
python screenstash.py scan        # Scan folder for existing screenshots
```

---

## ⚙️ Configuration

Settings are saved in `%LOCALAPPDATA%/ScreenStash/config.json`. You can also edit them directly from the **Settings & AI Model** drawer in the dashboard sidebar:

- **Screenshot Directory**: Defaults to your OS screenshot folder (with automatic OneDrive redirection support).
- **Ollama Endpoint**: Defaults to `http://localhost:11434`.
- **Ollama Model**: Defaults to `llama3:latest` (or `mistral`, `phi3`, etc.).
- **Tesseract Binary Path**: `C:\Program Files\Tesseract-OCR\tesseract.exe` (or `tesseract` on Linux/macOS).

---

## 🧪 Running Tests

To run the unit and integration test suite:
```bash
python -m unittest tests/test_pipeline.py
```

The test suite validates:
- SQLite table initialization, CRUD, and full-text search.
- Cryptographic deduplication (SHA-256).
- Heuristic fallback detection for Tasks, Receipts, and Events.
- Pydantic models and serialization properties.

---

## 📖 Mandatory Reference Files

- [Decisions.mc](file:///c:/PeassBeReasonable/Hacktoberfest/ScreenStash/Decisions.mc): Log of architectural decisions and concrete rationale.
- [Flow.md](file:///c:/PeassBeReasonable/Hacktoberfest/ScreenStash/Flow.md): Module-by-module execution trace and architecture diagram.
- [tech.md](file:///c:/PeassBeReasonable/Hacktoberfest/ScreenStash/tech.md): Technical interview style questions and deep answers covering concurrency, file stabilization, deduplication, and system design.
