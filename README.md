# 📸 ScreenStash — Screenshot-to-Plan Desktop MVP

> **Turn raw desktop screenshots into actionable tasks, calendar events, receipts, and organized knowledge automatically.**

ScreenStash is a local-first desktop application that runs silently in the background, detects whenever you take a screenshot, extracts its text using OCR, interprets and categorizes the information with local AI, and presents everything in an interactive desktop dashboard.

---

## ✨ Features

- ⚡ **Automatic Detection**: Monitors your operating system's default screenshot folder (`Win+PrtScn`, `Win+Shift+S`, Snipping Tool) with sub-second debounce protection.
- 🔍 **Local OCR & AI Pipeline**: Extracts text via Tesseract OCR and structures insights using local open-weight models via **Ollama**, with Gemma 3 as the default.
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
| **Local AI Engine** | Ollama (`gemma3:4b`) | Local model for structured JSON parsing |
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
- (Optional, Recommended) [Ollama](https://ollama.ai/); ScreenStash can download `gemma3:4b` for you

> **Note**: Even if you do not have Tesseract or Ollama installed yet, ScreenStash will gracefully run using its built-in fallback engine!

### 2. Installation & first-run onboarding

#### On Windows:
Choose either installation path:

**Download path**

1. Download `ScreenStash-Windows.zip` from the ScreenStash landing page.
2. Extract the ZIP to a folder you control.
3. Double-click `install.bat`.

**CLI path**

Open PowerShell or Command Prompt and run:

```bash
git clone https://github.com/guptapiyush16/ScreenStash.git
cd ScreenStash
python screenstash.py install
```

The installer installs the Python dependencies and opens the local ScreenStash onboarding screen. It does not start monitoring or register login startup before the onboarding is completed.

ScreenStash then opens a short onboarding screen that:
- Installs dependencies from `requirements.txt`
- Auto-detects your Windows screenshot folder (including OneDrive paths)
- Explains that screenshots may contain private information
- Lets you confirm or change the folder it watches
- Explains local AI processing and the optional model download
- Starts the background watcher after you confirm
- Adds Windows login startup only when you explicitly opt in

#### On macOS / Linux:
```bash
git clone https://github.com/guptapiyush16/ScreenStash.git
cd ScreenStash
python3 screenstash.py install
```
The app watches the folder you select during onboarding. It never takes screenshots itself.

### 3. Set up Ollama and Gemma 3 (optional local AI)

ScreenStash can use Ollama and the Gemma 3 model for structured extraction. This is an optional local enhancement; the offline fallback remains available if Ollama is not installed.

1. Install Ollama from [ollama.com/download](https://ollama.com/download).
2. Start Ollama if it is not already running.
3. From the ScreenStash folder, run:

```bash
python screenstash.py setup-ai gemma3:4b
```

This runs `ollama pull gemma3:4b` and shows Ollama's download progress. The model can require several gigabytes of disk space and the first download may take a while. ScreenStash stores the selected model in the local configuration and uses it through Ollama's local API at `http://localhost:11434`.

Verify the setup with:

```bash
ollama list
```

The dashboard shows whether the selected model is **Ready** or **Download needed**. ScreenStash does not send screenshots to a cloud AI service.

### 4. Background Service & Live Popups

Once setup is complete, ScreenStash runs 24/7 in the background:
1. **Take a screenshot normally** anywhere on your PC (`Win+Shift+S` or `Win+PrtScn`).
2. A subtle popup appears:
   **`ScreenStash is working` — Processing locally. Your screenshot stays on this device.**
3. Once processed, it updates to:
   **`Task found in your screenshot`** (or `Event`, `Receipt`, `Reference`).
4. Click the popup at any time to open your organized dashboard!

If you want the optional local Ollama model, run:
```bash
python screenstash.py setup-ai gemma3:4b
```
The command displays Ollama's download progress. If Ollama is unavailable, the built-in OCR/heuristic fallback remains usable.

### 5. CLI Control Center (`screenstash.py`)
```bash
python screenstash.py status      # Check if background service is running
python screenstash.py start       # Start background daemon
python screenstash.py stop        # Stop background daemon
python screenstash.py dashboard   # Open dashboard in browser
python screenstash.py scan        # Scan folder for existing screenshots
python screenstash.py setup-ai gemma3:4b  # Download the Gemma 3 local model
```

---

## ⚙️ Configuration

Settings are saved in `%LOCALAPPDATA%/ScreenStash/config.json`. You can also edit them directly from the **Settings & AI Model** drawer in the dashboard sidebar:

- **Screenshot Directory**: Defaults to your OS screenshot folder (with automatic OneDrive redirection support).
- **Ollama Endpoint**: Defaults to `http://localhost:11434`.
- **Ollama Model**: Defaults to `gemma3:4b`. You can also choose Llama 3.2 during onboarding.
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
