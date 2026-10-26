use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::{env, fs, path::{Path, PathBuf}, process::Command, sync::Mutex, time::Instant};
use tauri::Manager;
use url::Url;

const CLOUD_API_URL: &str = "https://screenstash-cloudapi.onrender.com";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub screenshot_dir: String, pub ollama_url: String, pub ollama_model: String,
    pub tesseract_cmd: String, pub auto_process_new_screenshots: bool,
    pub enable_fallback_heuristic_ai: bool, pub theme: String, pub onboarding_complete: bool,
    pub process_locally: bool, pub start_at_login: bool, pub notify_on_results: bool,
    #[serde(default = "default_ai_provider")] pub ai_provider: String,
    #[serde(default)] pub cloud_api_url: String,
    #[serde(default)] pub cloud_consent: bool,
    #[serde(default)] pub cloud_installation_id: String,
}
fn default_ai_provider() -> String { "offline".into() }
#[derive(Debug, Serialize)]
pub struct RuntimeStatus { service_running: bool, python_available: bool, ollama_available: bool, model_ready: bool, watched_folder: String, app_data_dir: String }
#[derive(Debug, Serialize)]
pub struct DashboardStats { total: u32, tasks: u32, events: u32, receipts: u32, processed_today: u32 }
#[derive(Debug, Serialize)]
pub struct StashItem {
    #[serde(default)]
    pub id: Option<i64>,
    pub title: String,
    pub category: String,
    pub summary: String,
    pub time: String,
    pub accent: String,
    #[serde(default)]
    pub file_path: Option<String>,
    #[serde(default)]
    pub file_name: Option<String>,
    #[serde(default)]
    pub raw_ocr_text: Option<String>,
    #[serde(default)]
    pub dates: Vec<String>,
    #[serde(default)]
    pub tasks: Vec<String>,
    #[serde(default)]
    pub amount: Option<String>,
}
fn app_data_dir() -> PathBuf {
    if cfg!(target_os = "windows") {
        return env::var_os("LOCALAPPDATA").or_else(|| env::var_os("APPDATA"))
            .map(PathBuf::from).unwrap_or_else(|| PathBuf::from(".")).join("ScreenStash");
    }
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    if cfg!(target_os = "macos") { home.join("Library").join("Application Support").join("ScreenStash") }
    else { env::var_os("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|| home.join(".local").join("share")).join("ScreenStash") }
}
fn config_path() -> PathBuf { app_data_dir().join("config.json") }
fn database_path() -> PathBuf { app_data_dir().join("screenstash.db") }
fn default_config() -> AppConfig {
    let home = env::var_os("USERPROFILE").or_else(|| env::var_os("HOME")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let screenshot_dir = home.join("Pictures").join("Screenshots");
    AppConfig { screenshot_dir: screenshot_dir.display().to_string(), ollama_url: "http://localhost:11434".into(), ollama_model: "gemma3:4b".into(), tesseract_cmd: "tesseract".into(), auto_process_new_screenshots: true, enable_fallback_heuristic_ai: true, theme: "light".into(), onboarding_complete: false, process_locally: true, start_at_login: false, notify_on_results: true, ai_provider: default_ai_provider(), cloud_api_url: CLOUD_API_URL.into(), cloud_consent: false, cloud_installation_id: String::new() }
}
fn read_config() -> AppConfig {
    fs::read_to_string(config_path()).ok().and_then(|text| serde_json::from_str::<AppConfig>(&text).ok()).map(|mut config| {
        if config.cloud_api_url.trim().is_empty() { config.cloud_api_url = CLOUD_API_URL.into(); }
        config
    }).unwrap_or_else(default_config)
}
fn python_executable() -> String { env::var("SCREENSTASH_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() }) }
fn project_root() -> PathBuf { env::var("SCREENSTASH_ROOT").map(PathBuf::from).unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../").to_path_buf()) }
#[tauri::command] fn get_config() -> AppConfig { read_config() }
fn validate_config(config: &AppConfig) -> Result<(), String> {
    let url = Url::parse(&config.ollama_url).map_err(|_| "Ollama endpoint must be a valid URL".to_string())?;
    if url.scheme() != "http" || !matches!(url.host_str(), Some("localhost") | Some("127.0.0.1") | Some("::1")) {
        return Err("Only a local Ollama endpoint is supported. Remote endpoints can expose screenshot text.".into());
    }
    if !matches!(config.ai_provider.as_str(), "offline" | "ollama" | "gemini") { return Err("Unsupported AI provider".into()); }
    if config.ai_provider == "gemini" {
        let cloud = Url::parse(&config.cloud_api_url).map_err(|_| "Cloud AI requires a valid HTTPS API URL".to_string())?;
        if cloud.as_str().trim_end_matches('/') != CLOUD_API_URL || !config.cloud_consent { return Err("Cloud AI uses the official HTTPS endpoint and requires explicit consent to upload screenshots".into()); }
    }
    Ok(())
}
static OLLAMA_CACHE: Mutex<Option<(Instant, bool, bool)>> = Mutex::new(None);
static PYTHON_CACHE: Mutex<Option<(Instant, bool)>> = Mutex::new(None);

fn is_pid_alive(pid: u32) -> bool {
    #[cfg(target_os = "windows")]
    {
        type HANDLE = *mut std::ffi::c_void;
        type BOOL = i32;
        type DWORD = u32;
        extern "system" {
            fn OpenProcess(dwDesiredAccess: DWORD, bInheritHandle: BOOL, dwProcessId: DWORD) -> HANDLE;
            fn CloseHandle(hObject: HANDLE) -> BOOL;
            fn GetExitCodeProcess(hProcess: HANDLE, lpExitCode: *mut DWORD) -> BOOL;
        }
        const PROCESS_QUERY_LIMITED_INFORMATION: DWORD = 0x1000;
        const STILL_ACTIVE: DWORD = 259;
        unsafe {
            let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if handle.is_null() {
                return false;
            }
            let mut exit_code: DWORD = 0;
            let ok = GetExitCodeProcess(handle, &mut exit_code);
            CloseHandle(handle);
            ok != 0 && exit_code == STILL_ACTIVE
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        let res = Command::new("kill").args(["-0", &pid.to_string()]).output();
        res.map(|o| o.status.success()).unwrap_or(false)
    }
}

fn check_service_running() -> bool {
    let pid_path = app_data_dir().join("screenstash_daemon.pid");
    if !pid_path.exists() {
        return false;
    }
    if let Ok(content) = fs::read_to_string(&pid_path) {
        if let Ok(pid) = content.trim().parse::<u32>() {
            if is_pid_alive(pid) {
                return true;
            }
            let _ = fs::remove_file(&pid_path);
        }
    }
    false
}

#[tauri::command]
fn save_config(config: AppConfig) -> Result<(), String> {
    validate_config(&config)?;
    let path = config_path();
    fs::create_dir_all(path.parent().unwrap_or(Path::new("."))).map_err(|e| e.to_string())?;
    fs::write(path, serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    // Invalidate ollama cache so next get_runtime_status reflects immediately
    if let Ok(mut cache) = OLLAMA_CACHE.lock() {
        *cache = None;
    }
    Ok(())
}
fn run_hidden_command(program: &str, args: &[&str]) -> Result<std::process::Output, std::io::Error> {
    let mut cmd = Command::new(program);
    cmd.args(args);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    cmd.output()
}

fn pipeline_process(app: &tauri::AppHandle, command: &str) -> Command {
    let sidecar_name = if cfg!(windows) { "screenstash-sidecar.exe" } else { "screenstash-sidecar" };
    let bundled_sidecar = app.path().resource_dir()
        .ok()
        .map(|dir| dir.join(sidecar_name))
        .filter(|path| path.exists());
    let mut process = if let Some(sidecar) = bundled_sidecar {
        let mut p = Command::new(sidecar);
        p.arg(command);
        p
    } else {
        let mut p = Command::new(python_executable());
        p.current_dir(project_root()).args(["screenstash.py", command]);
        p
    };
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        process.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    process
}
#[tauri::command]
fn get_runtime_status(_app: tauri::AppHandle) -> RuntimeStatus {
    let config = read_config();
    // Fix 2: Check service status directly via native PID (instant, 0 subprocesses)
    let service_running = check_service_running();

    // Fix 1: Check Ollama ONLY when "ollama" is selected in the AI provider dropdown
    let is_ollama_selected = config.ai_provider == "ollama";
    let (ollama_available, model_ready) = if is_ollama_selected {
        let mut cache = OLLAMA_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        if let Some((time, avail, ready)) = *cache {
            if time.elapsed().as_secs() < 30 {
                (avail, ready)
            } else {
                let avail = run_hidden_command("ollama", &["--version"]).is_ok();
                let ready = if avail {
                    if let Ok(output) = run_hidden_command("ollama", &["list"]) {
                        let text = String::from_utf8_lossy(&output.stdout);
                        text.contains(&config.ollama_model) || (config.ollama_model.contains("gemma3") && text.contains("gemma3"))
                    } else { false }
                } else { false };
                *cache = Some((Instant::now(), avail, ready));
                (avail, ready)
            }
        } else {
            let avail = run_hidden_command("ollama", &["--version"]).is_ok();
            let ready = if avail {
                if let Ok(output) = run_hidden_command("ollama", &["list"]) {
                    let text = String::from_utf8_lossy(&output.stdout);
                    text.contains(&config.ollama_model) || (config.ollama_model.contains("gemma3") && text.contains("gemma3"))
                } else { false }
            } else { false };
            *cache = Some((Instant::now(), avail, ready));
            (avail, ready)
        }
    } else {
        // When Offline or Cloud is selected, zero Ollama commands are spawned!
        (false, false)
    };

    // Cached Python availability (valid for 120s)
    let python_available = {
        let mut py_cache = PYTHON_CACHE.lock().unwrap_or_else(|e| e.into_inner());
        if let Some((time, ok)) = *py_cache {
            if time.elapsed().as_secs() < 120 {
                ok
            } else {
                let ok = run_hidden_command(&python_executable(), &["--version"]).is_ok();
                *py_cache = Some((Instant::now(), ok));
                ok
            }
        } else {
            let ok = run_hidden_command(&python_executable(), &["--version"]).is_ok();
            *py_cache = Some((Instant::now(), ok));
            ok
        }
    };

    RuntimeStatus {
        service_running,
        python_available,
        ollama_available,
        model_ready,
        watched_folder: config.screenshot_dir,
        app_data_dir: app_data_dir().display().to_string(),
    }
}
#[tauri::command]
fn get_dashboard_stats() -> DashboardStats {
    let Ok(conn) = Connection::open(database_path()) else { return DashboardStats { total: 0, tasks: 0, events: 0, receipts: 0, processed_today: 0 }; };
    let total = conn.query_row("SELECT COUNT(*) FROM screenshots", [], |row| row.get::<_, u32>(0)).unwrap_or(0);
    let count = |category: &str| conn.query_row("SELECT COUNT(*) FROM screenshots WHERE status = 'PROCESSED' AND category = ?1", [category], |row| row.get::<_, u32>(0)).unwrap_or(0);
    let processed_today = conn.query_row("SELECT COUNT(*) FROM screenshots WHERE status = 'PROCESSED' AND date(processed_at, 'localtime') = date('now', 'localtime')", [], |row| row.get::<_, u32>(0)).unwrap_or(0);
    DashboardStats { total, tasks: count("Task"), events: count("Event"), receipts: count("Receipt"), processed_today }
}
#[tauri::command]
fn get_recent_items() -> Vec<StashItem> {
    let Ok(conn) = Connection::open(database_path()) else { return Vec::new(); };
    let Ok(mut statement) = conn.prepare("SELECT id, title, category, summary, created_at, file_path, file_name, raw_ocr_text, dates_json, tasks_json, amount FROM screenshots ORDER BY created_at DESC LIMIT 100") else { return Vec::new(); };
    let Ok(rows) = statement.query_map([], |row| {
        let id: Option<i64> = row.get(0).ok();
        let title: String = row.get(1)?;
        let category: String = row.get(2)?;
        let summary: String = row.get(3)?;
        let time: String = row.get(4)?;
        let file_path: Option<String> = row.get(5).ok();
        let file_name: Option<String> = row.get(6).ok();
        let raw_ocr_text: Option<String> = row.get(7).ok();
        let dates_raw: Option<String> = row.get(8).ok();
        let tasks_raw: Option<String> = row.get(9).ok();
        let amount: Option<String> = row.get(10).ok();
        let dates: Vec<String> = dates_raw.and_then(|r| serde_json::from_str(&r).ok()).unwrap_or_default();
        let tasks: Vec<String> = tasks_raw.and_then(|r| serde_json::from_str(&r).ok()).unwrap_or_default();
        let accent = match category.as_str() {
            "Task" => "peach",
            "Event" => "purple",
            "Receipt" => "green",
            _ => "lime",
        }.to_string();
        Ok(StashItem { id, title, category, summary, time, accent, file_path, file_name, raw_ocr_text, dates, tasks, amount })
    }) else { return Vec::new(); };
    rows.filter_map(Result::ok).collect()
}

#[tauri::command]
fn open_file_in_folder(path: String) -> Result<(), String> {
    if path.is_empty() { return Err("Path is empty".into()); }
    let p = PathBuf::from(&path);
    if !p.exists() { return Err("File does not exist".into()); }
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("explorer").args(["/select,", &path]).spawn().map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").args(["-R", &path]).spawn().map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        if let Some(parent) = p.parent() {
            let _ = Command::new("xdg-open").arg(parent).spawn().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

#[tauri::command]
fn delete_screenshot_item(id: i64) -> Result<(), String> {
    let conn = Connection::open(database_path()).map_err(|e| e.to_string())?;
    conn.execute("DELETE FROM screenshots WHERE id = ?1", [id]).map_err(|e| e.to_string())?;
    Ok(())
}
#[tauri::command]
fn run_pipeline_command(app: tauri::AppHandle, command: String) -> Result<String, String> {
    let allowed = ["start", "stop", "setup-ai"];
    if !allowed.contains(&command.as_str()) {
        return Err("Unsupported pipeline command".into());
    }
    let mut process = pipeline_process(&app, &command);
    if command == "start" {
        process.spawn().map_err(|e| e.to_string())?;
        return Ok("Background watcher started.".into());
    }
    let output = process.output().map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    if output.status.success() {
        Ok(stdout)
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

fn base64_encode(data: &[u8]) -> String {
    const CHARSET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut result = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0];
        let b1 = if chunk.len() > 1 { chunk[1] } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] } else { 0 };
        result.push(CHARSET[(b0 >> 2) as usize] as char);
        result.push(CHARSET[(((b0 & 0x03) << 4) | (b1 >> 4)) as usize] as char);
        if chunk.len() > 1 {
            result.push(CHARSET[(((b1 & 0x0f) << 2) | (b2 >> 6)) as usize] as char);
        } else {
            result.push('=');
        }
        if chunk.len() > 2 {
            result.push(CHARSET[(b2 & 0x3f) as usize] as char);
        } else {
            result.push('=');
        }
    }
    result
}

#[tauri::command]
fn read_screenshot_image(path: String) -> Result<String, String> {
    if path.trim().is_empty() {
        return Err("Path is empty".into());
    }
    let p = PathBuf::from(&path);
    if !p.exists() {
        return Err(format!("Screenshot file does not exist: {}", path));
    }

    let ext = p.extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    let mime = match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "bmp" => "image/bmp",
        _ => "image/png",
    };

    let bytes = fs::read(&p).map_err(|e| format!("Failed to read screenshot file: {}", e))?;
    let b64 = base64_encode(&bytes);
    Ok(format!("data:{};base64,{}", mime, b64))
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            get_runtime_status,
            get_dashboard_stats,
            get_recent_items,
            run_pipeline_command,
            open_file_in_folder,
            delete_screenshot_item,
            read_screenshot_image
        ])
        .setup(|app| {
            let _ = app.handle();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running ScreenStash");
}
