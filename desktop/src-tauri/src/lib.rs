use serde::{Deserialize, Serialize};
use std::{env, fs, path::{Path, PathBuf}, process::Command};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub screenshot_dir: String, pub ollama_url: String, pub ollama_model: String,
    pub tesseract_cmd: String, pub auto_process_new_screenshots: bool,
    pub enable_fallback_heuristic_ai: bool, pub theme: String, pub onboarding_complete: bool,
    pub process_locally: bool, pub start_at_login: bool, pub notify_on_results: bool,
}
#[derive(Debug, Serialize)]
pub struct RuntimeStatus { service_running: bool, python_available: bool, ollama_available: bool, watched_folder: String, app_data_dir: String }
#[derive(Debug, Serialize)]
pub struct DashboardStats { total: u32, tasks: u32, events: u32, receipts: u32 }
fn app_data_dir() -> PathBuf { if let Some(local) = env::var_os("LOCALAPPDATA") { return PathBuf::from(local).join("ScreenStash"); } env::var_os("APPDATA").map(PathBuf::from).unwrap_or_else(|| PathBuf::from(".")).join("ScreenStash") }
fn config_path() -> PathBuf { app_data_dir().join("config.json") }
fn default_config() -> AppConfig {
    let home = env::var_os("USERPROFILE").or_else(|| env::var_os("HOME")).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let screenshot_dir = home.join("Pictures").join("Screenshots");
    AppConfig { screenshot_dir: screenshot_dir.display().to_string(), ollama_url: "http://localhost:11434".into(), ollama_model: "gemma3:4b".into(), tesseract_cmd: "tesseract".into(), auto_process_new_screenshots: true, enable_fallback_heuristic_ai: true, theme: "light".into(), onboarding_complete: false, process_locally: true, start_at_login: false, notify_on_results: true }
}
fn read_config() -> AppConfig { fs::read_to_string(config_path()).ok().and_then(|text| serde_json::from_str(&text).ok()).unwrap_or_else(default_config) }
fn python_executable() -> String { env::var("SCREENSTASH_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python".into() } else { "python3".into() }) }
fn project_root() -> PathBuf { env::var("SCREENSTASH_ROOT").map(PathBuf::from).unwrap_or_else(|_| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../").to_path_buf()) }
#[tauri::command] fn get_config() -> AppConfig { read_config() }
#[tauri::command] fn save_config(config: AppConfig) -> Result<(), String> { let path = config_path(); fs::create_dir_all(path.parent().unwrap_or(Path::new("."))).map_err(|e| e.to_string())?; fs::write(path, serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?).map_err(|e| e.to_string()) }
#[tauri::command] fn get_runtime_status() -> RuntimeStatus { let config = read_config(); RuntimeStatus { service_running: false, python_available: Command::new(python_executable()).arg("--version").output().is_ok(), ollama_available: Command::new("ollama").arg("--version").output().is_ok(), watched_folder: config.screenshot_dir, app_data_dir: app_data_dir().display().to_string() } }
#[tauri::command]
fn get_dashboard_stats() -> DashboardStats {
    let script = "import database, json; database.init_db(); print(json.dumps(database.get_stats()))";
    let output = Command::new(python_executable()).current_dir(project_root())
        .args(["-c", script]).output();
    if let Ok(output) = output {
        if output.status.success() {
            if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&output.stdout) {
                let categories = value.get("categories").unwrap_or(&serde_json::Value::Null);
                return DashboardStats {
                    total: value.get("total").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    tasks: categories.get("Task").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    events: categories.get("Event").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                    receipts: categories.get("Receipt").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                };
            }
        }
    }
    DashboardStats { total: 0, tasks: 0, events: 0, receipts: 0 }
}
#[tauri::command] fn run_pipeline_command(command: String) -> Result<String, String> { let allowed = ["start", "stop", "scan", "setup-ai"]; if !allowed.contains(&command.as_str()) { return Err("Unsupported pipeline command".into()); } let output = Command::new(python_executable()).current_dir(project_root()).args(["screenstash.py", &command]).output().map_err(|e| e.to_string())?; let stdout = String::from_utf8_lossy(&output.stdout).to_string(); if output.status.success() { Ok(stdout) } else { Err(String::from_utf8_lossy(&output.stderr).to_string()) } }
pub fn run() { tauri::Builder::default().invoke_handler(tauri::generate_handler![get_config, save_config, get_runtime_status, get_dashboard_stats, run_pipeline_command]).setup(|app| { let _ = app.handle(); Ok(()) }).run(tauri::generate_context!()).expect("error while running ScreenStash"); }
