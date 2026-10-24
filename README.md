# ScreenStash

ScreenStash is a downloadable Tauri desktop application for Windows and macOS. It watches a user-selected screenshot folder, extracts text locally, and stores organized results in a local SQLite database.

## Install

Download the `.exe` or `.dmg` from the landing page or GitHub Releases. The distributed application does not require Python or a source checkout.

## Processing choices

- **Built-in offline engine:** Tesseract OCR plus local heuristics. It needs no account, model download, or network connection.
- **Gemma 3 or Llama 3.2:** optional local models run through Ollama. Install Ollama once from its official download page, select a model in Settings, then let ScreenStash download it locally.

ScreenStash accepts only loopback Ollama endpoints (`localhost`, `127.0.0.1`, or `::1`) so screenshot text cannot be sent to a remote Ollama server by configuration.

## Development

The React/Tauri UI lives in `desktop/`; Python is packaged only as the processing sidecar.

```powershell
cd desktop
npm ci
npm run tauri:dev
```

Run the Python tests with:

```powershell
python -m unittest tests/test_pipeline.py
```

## Release

`.github/workflows/desktop-release.yml` builds the Windows installer and macOS disk image, packaging the Python processor as a sidecar. Production releases should be code-signed (and macOS releases notarized) before publishing.
