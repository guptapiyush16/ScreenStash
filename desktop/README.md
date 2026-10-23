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

The current migration shell uses the existing Python pipeline through a local
bridge. A production installer must package a Python runtime and the pipeline
sidecar before distribution; the release workflow currently builds the Tauri
shell and should be treated as a migration preview until that sidecar packaging
step is completed.
