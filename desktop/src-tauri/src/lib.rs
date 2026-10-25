use serde::{Deserialize, Serialize};
use rusqlite::Connection;
use std::{env, fs, path::{Path, PathBuf}, process::Command};
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
    pub title: String,
    pub category: String,
    pub summary: String,
    pub time: String,
    pub accent: String,
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
#[tauri::command] fn save_config(config: AppConfig) -> Result<(), String> { validate_config(&config)?; let path = config_path(); fs::create_dir_all(path.parent().unwrap_or(Path::new("."))).map_err(|e| e.to_string())?; fs::write(path, serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?).map_err(|e| e.to_string()) }
fn pipeline_process(app: &tauri::AppHandle, command: &str) -> Command {
    let sidecar_name = if cfg!(windows) { "screenstash-sidecar.exe" } else { "screenstash-sidecar" };
    let bundled_sidecar = app.path().resource_dir()
        .ok()
        .map(|dir| dir.join(sidecar_name))
        .filter(|path| path.exists());
    if let Some(sidecar) = bundled_sidecar {
        let mut process = Command::new(sidecar);
        process.arg(command);
        process
    } else {
        let mut process = Command::new(python_executable());
        process.current_dir(project_root()).args(["screenstash.py", command]);
        process
    }
}
#[tauri::command]
fn get_runtime_status(app: tauri::AppHandle) -> RuntimeStatus {
    let config = read_config();
    // Ask the Python sidecar to validate the PID and its command line. A PID
    // file by itself can outlive a crashed watcher and must not be treated as
    // proof that screenshots are being monitored.
    let service_running = pipeline_process(&app, "status").output().map(|output| output.status.success()).unwrap_or(false);
    let ollama_available = Command::new("ollama").arg("--version").output().is_ok();
    let model_ready = if ollama_available {
        if let Ok(output) = Command::new("ollama").arg("list").output() {
            let text = String::from_utf8_lossy(&output.stdout);
            text.contains(&config.ollama_model) || (config.ollama_model.contains("gemma3") && text.contains("gemma3"))
        } else {
            false
        }
    } else {
        false
    };
    RuntimeStatus {
        service_running,
        python_available: Command::new(python_executable()).arg("--version").output().is_ok(),
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
    let Ok(mut statement) = conn.prepare("SELECT title, category, summary, created_at, dates_json, tasks_json, amount FROM screenshots ORDER BY created_at DESC LIMIT 100") else { return Vec::new(); };
    let Ok(rows) = statement.query_map([], |row| {
        let title: String = row.get(0)?;
        let category: String = row.get(1)?;
        let summary: String = row.get(2)?;
        let time: String = row.get(3)?;
        let dates_raw: Option<String> = row.get(4).ok();
        let tasks_raw: Option<String> = row.get(5).ok();
        let amount: Option<String> = row.get(6).ok();
        let dates: Vec<String> = dates_raw.and_then(|r| serde_json::from_str(&r).ok()).unwrap_or_default();
        let tasks: Vec<String> = tasks_raw.and_then(|r| serde_json::from_str(&r).ok()).unwrap_or_default();
        let accent = match category.as_str() {
            "Task" => "peach",
            "Event" => "purple",
            "Receipt" => "green",
            _ => "lime",
        }.to_string();
        Ok(StashItem { title, category, summary, time, accent, dates, tasks, amount })
    }) else { return Vec::new(); };
    rows.filter_map(Result::ok).collect()
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
pub fn run() { tauri::Builder::default().invoke_handler(tauri::generate_handler![get_config, save_config, get_runtime_status, get_dashboard_stats, get_recent_items, run_pipeline_command]).setup(|app| { let _ = app.handle(); Ok(()) }).run(tauri::generate_context!()).expect("error while running ScreenStash"); }
