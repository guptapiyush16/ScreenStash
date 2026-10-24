export type Category = "Task" | "Event" | "Receipt" | "Reference" | "Other";
export interface AppConfig {
  screenshot_dir: string; ollama_url: string; ollama_model: string; tesseract_cmd: string;
  auto_process_new_screenshots: boolean; enable_fallback_heuristic_ai: boolean;
  theme: "light" | "dark"; onboarding_complete: boolean; process_locally: boolean;
  start_at_login: boolean; notify_on_results: boolean;
  ai_provider: "offline" | "ollama" | "gemini"; cloud_api_url: string;
  cloud_consent: boolean; cloud_installation_id: string;
}
export interface RuntimeStatus {
  service_running: boolean; python_available: boolean; ollama_available: boolean;
  model_ready: boolean; watched_folder: string; app_data_dir: string;
}
export interface DashboardStats { total: number; tasks: number; events: number; receipts: number; }
export interface StashItem { title: string; category: Category; summary: string; time: string; accent: string; }
