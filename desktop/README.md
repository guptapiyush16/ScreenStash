# ScreenStash Desktop (Tauri 2)

This directory is the production migration shell for ScreenStash. The React/Vite
frontend owns the desktop experience while the existing Python OCR, heuristic AI,
SQLite, and watcher modules remain the local pipeline/sidecar.

```powershell
cd desktop
npm install
npm run dev
npm run tauri:dev
npm run build
npm run tauri:build
```

The Rust bridge uses `SCREENSTASH_ROOT` to locate the repository and
`SCREENSTASH_PYTHON` to select the Python executable. Set both when running a
packaged build outside the repository. Pipeline commands are whitelisted.

The release workflow packages the Python processing pipeline as
`screenstash-sidecar.exe` and includes it in the Tauri installer. Ollama and
Tesseract remain optional local dependencies: without them, ScreenStash uses
the built-in fallback engine and reports the degraded status in the app.
