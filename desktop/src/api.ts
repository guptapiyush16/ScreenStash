import { invoke } from "@tauri-apps/api/core";
import type { AppConfig, DashboardStats, RuntimeStatus, StashItem } from "./types";
const isTauri = Boolean((window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__);
export async function getConfig(): Promise<AppConfig | null> { return isTauri ? invoke<AppConfig>("get_config") : null; }
export async function saveConfig(config: AppConfig): Promise<void> { if (isTauri) await invoke("save_config", { config }); }
export async function getRuntimeStatus(): Promise<RuntimeStatus | null> { return isTauri ? invoke<RuntimeStatus>("get_runtime_status") : null; }
export async function getDashboardStats(): Promise<DashboardStats | null> { return isTauri ? invoke<DashboardStats>("get_dashboard_stats") : null; }
export async function getRecentItems(): Promise<StashItem[]> { return isTauri ? invoke<StashItem[]>("get_recent_items") : []; }
export async function runPipelineCommand(command: "start" | "stop" | "scan" | "setup-ai"): Promise<string> {
  return isTauri ? invoke<string>("run_pipeline_command", { command }) : "Desktop shell preview mode";
}
