import { useEffect, useMemo, useState, useCallback } from "react";
import {
  deleteScreenshot,
  getConfig,
  getDashboardStats,
  getRecentItems,
  getRuntimeStatus,
  getScreenshotAssetUrl,
  loadScreenshotDataUrl,
  openFileInFolder,
  runPipelineCommand,
  saveConfig
} from "./api";
import type { AppConfig, DashboardStats, RuntimeStatus, StashItem } from "./types";
import { MonthlyCalendar } from "./Calendar";
import {
  evaluateNeedsAttention,
  evaluateSavedForLater,
  evaluateSemanticScore,
  executeAiFilter
} from "./aiFilter";

const CLOUD_API_URL = "https://screenstash-cloudapi.onrender.com";
const defaultConfig: AppConfig = {
  screenshot_dir: "Detecting your Screenshots folder…",
  ollama_url: "http://localhost:11434",
  ollama_model: "gemma3:4b",
  tesseract_cmd: "tesseract",
  auto_process_new_screenshots: true,
  enable_fallback_heuristic_ai: true,
  theme: "light",
  onboarding_complete: false,
  process_locally: true,
  start_at_login: false,
  notify_on_results: true,
  ai_provider: "offline",
  cloud_api_url: CLOUD_API_URL,
  cloud_consent: false,
  cloud_installation_id: ""
};
const emptyStats: DashboardStats = { total: 0, tasks: 0, events: 0, receipts: 0, processed_today: 0 };

type Timeframe = "today" | "7days" | "30days" | "month" | "all";
const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  today: "Today",
  "7days": "Last 7 days",
  "30days": "Last 30 days",
  month: "This month",
  all: "All time"
};

type SmartFilter = "none" | "attention" | "saved" | "today";

function App() {
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [stats, setStats] = useState<DashboardStats>(emptyStats);
  const [view, setView] = useState<"overview" | "tasks" | "calendar" | "settings">("overview");
  const [items, setItems] = useState<StashItem[]>([]);
  const [onboarding, setOnboarding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [cloudStatus, setCloudStatus] = useState<"checking" | "connected" | "error" | "idle">("idle");

  // New interactive states
  const [searchQuery, setSearchQuery] = useState("");
  const [timeframe, setTimeframe] = useState<Timeframe>("7days");
  const [smartFilter, setSmartFilter] = useState<SmartFilter>("none");
  const [lightboxItem, setLightboxItem] = useState<StashItem | null>(null);
  const [aiFilterActive, setAiFilterActive] = useState(true);
  const [deepAiLoading, setDeepAiLoading] = useState(false);
  const [deepAiEngine, setDeepAiEngine] = useState("");
  const [deepAiResults, setDeepAiResults] = useState<{
    matchedKeys: Set<string>;
    reasons: Record<string, string>;
  } | null>(null);

  async function checkCloudConnection() {
    setCloudStatus("checking");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 35000);
    try {
      const res = await fetch("https://screenstash-cloudapi.onrender.com/health", {
        method: "GET",
        signal: controller.signal
      });
      const health = (await res.json()) as { status?: string; gemini_configured?: boolean };
      if (res.ok && health.status === "ok" && health.gemini_configured !== false) {
        setCloudStatus("connected");
      } else {
        setCloudStatus("error");
      }
    } catch {
      setCloudStatus("error");
    } finally {
      clearTimeout(timer);
    }
  }

  useEffect(() => {
    if (config.ai_provider === "gemini") {
      checkCloudConnection();
    } else {
      setCloudStatus("idle");
    }
  }, [config.ai_provider]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getConfig(), getRuntimeStatus(), getDashboardStats(), getRecentItems()])
      .then(async ([loaded, runtime, loadedStats, loadedItems]) => {
        if (cancelled) return;
        if (loaded) {
          setConfig(loaded);
          setOnboarding(!loaded.onboarding_complete);
        }
        setStatus(runtime);
        if (loadedStats) setStats(loadedStats);
        setItems(loadedItems);
        if (loaded?.onboarding_complete && !runtime?.service_running) {
          try {
            await runPipelineCommand("start");
            await new Promise((resolve) => window.setTimeout(resolve, 750));
            if (!cancelled) {
              const recovered = await getRuntimeStatus();
              setStatus(recovered);
              setNotice("Screenshot watcher restarted.");
            }
          } catch {
            if (!cancelled) {
              setNotice("The screenshot watcher could not start. Check the selected folder and restart ScreenStash.");
            }
          }
        }
      })
      .catch(() => setNotice("Running in preview mode — connect the Python sidecar to load live data."));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let isPolling = false;
    let pollTick = 0;

    const interval = setInterval(async () => {
      if (isPolling) return; // Fix 3: Concurrency guard against stacked promises
      isPolling = true;
      pollTick++;
      try {
        // Fast local SQLite queries (<1ms)
        const [latestStats, latestItems] = await Promise.all([
          getDashboardStats(),
          getRecentItems()
        ]);
        if (active) {
          if (latestStats) setStats(latestStats);
          if (latestItems) setItems(latestItems);
        }

        // Periodic runtime status check every 4th cycle (~20s) to keep CPU 0%
        if (pollTick % 4 === 0) {
          const latestRuntime = await getRuntimeStatus();
          if (active && latestRuntime) setStatus(latestRuntime);
        }
      } catch {
        // Silently skip if bridge is busy
      } finally {
        isPolling = false;
      }
    }, 5000);

    const onFocus = () => {
      if (isPolling) return;
      isPolling = true;
      Promise.all([getDashboardStats(), getRecentItems(), getRuntimeStatus()])
        .then(([s, i, r]) => {
          if (s) setStats(s);
          if (i) setItems(i);
          if (r) setStatus(r);
        })
        .catch(() => undefined)
        .finally(() => {
          isPolling = false;
        });
    };

    window.addEventListener("focus", onFocus);
    return () => {
      active = false;
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  async function refreshDashboard() {
    try {
      const [s, i, r] = await Promise.all([getDashboardStats(), getRecentItems(), getRuntimeStatus()]);
      if (s) setStats(s);
      if (i) setItems(i);
      if (r) setStatus(r);
      setNotice("Dashboard status refreshed.");
    } catch {
      setNotice("Could not refresh dashboard.");
    }
  }

  async function handleDeleteItem(itemToDelete: StashItem) {
    if (itemToDelete.id) {
      await deleteScreenshot(itemToDelete.id);
    }
    setItems((prev) => prev.filter((i) => i.title !== itemToDelete.title || i.time !== itemToDelete.time));
    setNotice(`Removed "${itemToDelete.title}" from your workspace.`);
    refreshDashboard().catch(() => undefined);
  }

  // Smart collection counts evaluated by AI
  const needsAttentionCount = useMemo(
    () => items.filter((i) => evaluateNeedsAttention(i).needsAttention).length,
    [items]
  );
  const savedForLaterCount = useMemo(
    () => items.filter((i) => evaluateSavedForLater(i).isSaved).length,
    [items]
  );

  async function triggerDeepAiFilter() {
    if (!searchQuery.trim()) return;
    setDeepAiLoading(true);
    setNotice("Running deep AI neural reasoning across your stash…");
    try {
      const res = await executeAiFilter(searchQuery, items, config, status);
      setDeepAiResults({ matchedKeys: res.matchedKeys, reasons: res.reasons });
      setDeepAiEngine(res.engine);
      setNotice(`AI Filter complete (${res.engine}): found ${res.matchedKeys.size} matches.`);
    } catch {
      setNotice("AI semantic search active (fallback engine).");
    } finally {
      setDeepAiLoading(false);
    }
  }

  // Combined Filtering Pipeline: Timeframe -> View -> SmartFilter -> SearchQuery (with AI/LLM semantic reasoning)
  const { visibleItems, itemAiReasons } = useMemo(() => {
    let list = items;
    const reasonsMap: Record<string, string> = {};

    // 1. Timeframe filter
    if (timeframe !== "all") {
      const now = new Date();
      let threshold = new Date();
      if (timeframe === "today") {
        threshold.setHours(0, 0, 0, 0);
      } else if (timeframe === "7days") {
        threshold.setDate(now.getDate() - 7);
      } else if (timeframe === "30days") {
        threshold.setDate(now.getDate() - 30);
      } else if (timeframe === "month") {
        threshold = new Date(now.getFullYear(), now.getMonth(), 1);
      }

      list = list.filter((item) => {
        if (!item.time) return true;
        const itemDate = new Date(item.time);
        if (isNaN(itemDate.getTime())) return true;
        return itemDate >= threshold;
      });
    }

    // 2. Navigation View filter (Action Items view filtered by AI tasks)
    if (view === "tasks") {
      list = list.filter((item) => {
        const hasTasks = Boolean(item.tasks && item.tasks.length > 0);
        const isTaskCat = item.category === "Task";
        if (hasTasks || isTaskCat) {
          reasonsMap[`${item.title}-${item.time}`] = hasTasks
            ? `${item.tasks?.length} actionable task(s)`
            : "Task category";
          return true;
        }
        return false;
      });
    }

    // 3. Smart Collection filter (AI / LLM evaluated)
    if (smartFilter === "attention") {
      list = list.filter((item) => {
        const aiEval = evaluateNeedsAttention(item);
        if (aiEval.needsAttention) {
          reasonsMap[`${item.title}-${item.time}`] = aiEval.reason;
          return true;
        }
        return false;
      });
    } else if (smartFilter === "saved") {
      list = list.filter((item) => {
        const aiEval = evaluateSavedForLater(item);
        if (aiEval.isSaved) {
          reasonsMap[`${item.title}-${item.time}`] = aiEval.reason;
          return true;
        }
        return false;
      });
    } else if (smartFilter === "today") {
      const todayStr = new Date().toISOString().slice(0, 10);
      list = list.filter((item) => {
        const isToday = item.time && item.time.startsWith(todayStr);
        if (isToday) {
          reasonsMap[`${item.title}-${item.time}`] = "Processed today";
          return true;
        }
        return false;
      });
    }

    // 4. Live Search Query filter (AI / LLM Semantic vs Substring)
    if (searchQuery.trim()) {
      if (deepAiResults) {
        // Explicit Neural LLM result (Ollama or Cloud)
        list = list.filter((item, idx) => {
          const key = `${item.title}-${item.time || idx}`;
          if (deepAiResults.matchedKeys.has(key)) {
            reasonsMap[`${item.title}-${item.time}`] =
              deepAiResults.reasons[key] || "Matched by Neural LLM";
            return true;
          }
          return false;
        });
      } else if (aiFilterActive) {
        // Realtime On-Device Semantic Intent AI
        const q = searchQuery.trim();
        list = list.filter((item) => {
          const { score, reason } = evaluateSemanticScore(item, q);
          if (score >= 25) {
            reasonsMap[`${item.title}-${item.time}`] = reason;
            return true;
          }
          return false;
        });
      } else {
        // Standard substring fallback
        const q = searchQuery.toLowerCase().trim();
        list = list.filter((item) => {
          const titleMatch = item.title.toLowerCase().includes(q);
          const summaryMatch = item.summary?.toLowerCase().includes(q);
          const catMatch = item.category?.toLowerCase().includes(q);
          const ocrMatch = item.raw_ocr_text?.toLowerCase().includes(q);
          const tasksMatch = item.tasks?.some((t) => t.toLowerCase().includes(q));
          const datesMatch = item.dates?.some((d) => d.toLowerCase().includes(q));
          return titleMatch || summaryMatch || catMatch || ocrMatch || tasksMatch || datesMatch;
        });
      }
    }

    return { visibleItems: list, itemAiReasons: reasonsMap };
  }, [items, timeframe, view, smartFilter, searchQuery, aiFilterActive, deepAiResults]);

  // Dynamic timeframe stats calculated from timeframe-filtered items
  const currentMetrics = useMemo(() => {
    const total = visibleItems.length;
    const tasks = visibleItems.filter((i) => i.category === "Task").length;
    const events = visibleItems.filter((i) => i.category === "Event").length;
    const receipts = visibleItems.filter((i) => i.category === "Receipt").length;
    return { total, tasks, events, receipts };
  }, [visibleItems]);

  async function finishOnboarding() {
    const next = { ...config, onboarding_complete: true };
    setConfig(next);
    setOnboarding(false);
    setSaving(true);
    try {
      await saveConfig(next);
      await runPipelineCommand("start");
      setNotice("ScreenStash is ready and watching locally.");
    } catch {
      setNotice("Saved locally. The Python watcher will start when the sidecar is available.");
    } finally {
      setSaving(false);
    }
  }

  async function updateConfig(patch: Partial<AppConfig>) {
    const next = { ...config, ...patch };
    const screenshotFolderChanged =
      patch.screenshot_dir !== undefined && patch.screenshot_dir.trim() !== config.screenshot_dir;
    const aiProviderChangedToOllama = patch.ai_provider === "ollama";
    setConfig(next);
    setSaving(true);
    try {
      await saveConfig(next);
      if (screenshotFolderChanged) {
        await runPipelineCommand("start").catch(() => undefined);
        const runtime = await getRuntimeStatus();
        if (runtime) setStatus(runtime);
        setNotice(`Now watching ${next.screenshot_dir}. Only new screenshots will be organized.`);
      } else if (aiProviderChangedToOllama) {
        // Fix 1 requirement: check Ollama immediately when user selects Ollama in the dropdown
        setNotice("Checking Ollama status & models on this PC…");
        const runtime = await getRuntimeStatus();
        if (runtime) setStatus(runtime);
        if (runtime?.model_ready) {
          setNotice(`Ollama connected: ${next.ollama_model} is ready.`);
        } else if (runtime?.ollama_available) {
          setNotice("Ollama detected. Click 'Download model' below to download weights.");
        } else {
          setNotice("Ollama not found on PATH. Install Ollama to run local models.");
        }
      } else {
        setNotice("Preferences saved.");
      }
    } catch (error) {
      setNotice(typeof error === "string" && error ? error : "Could not save the setting. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSetupAi() {
    setNotice("Downloading the selected local model. This can take a few minutes; keep ScreenStash open.");
    try {
      await runPipelineCommand("setup-ai");
      setNotice("Ollama model downloaded successfully! Local AI is active.");
      const updatedStatus = await getRuntimeStatus();
      if (updatedStatus) setStatus(updatedStatus);
    } catch {
      setNotice("The model download failed. Check that Ollama is installed and running; the offline engine remains available.");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">✦</div>
          <span>ScreenStash</span>
        </div>
        <p className="eyebrow">YOUR WORKSPACE</p>
        <nav>
          <NavButton
            active={view === "overview" && smartFilter === "none"}
            icon="⌂"
            label="Overview"
            onClick={() => {
              setView("overview");
              setSmartFilter("none");
            }}
          />
          <NavButton
            active={view === "tasks"}
            icon="✓"
            label="Tasks"
            badge={stats.tasks}
            onClick={() => {
              setView("tasks");
              setSmartFilter("none");
            }}
          />
          <NavButton
            active={view === "calendar"}
            icon="□"
            label="Calendar"
            onClick={() => {
              setView("calendar");
              setSmartFilter("none");
            }}
          />
          <NavButton
            active={false}
            icon="⌁"
            label="References"
            onClick={() => {
              setView("overview");
              setSmartFilter("saved");
            }}
          />
          <NavButton
            active={false}
            icon="▦"
            label="All screenshots"
            onClick={() => {
              setView("overview");
              setTimeframe("all");
              setSmartFilter("none");
              setNotice(`${stats.total} total screenshot(s) are stored locally.`);
            }}
          />
        </nav>

        <p className="eyebrow smart-label">SMART COLLECTIONS</p>
        <button
          className={`smart-item-btn ${smartFilter === "attention" ? "active" : ""}`}
          onClick={() => {
            setView("overview");
            setSmartFilter((cur) => (cur === "attention" ? "none" : "attention"));
          }}
          title="Filter to tasks needing attention"
        >
          <i className="dot peach" />
          <span>Needs attention</span>
          <em>{needsAttentionCount}</em>
        </button>
        <button
          className={`smart-item-btn ${smartFilter === "saved" ? "active" : ""}`}
          onClick={() => {
            setView("overview");
            setSmartFilter((cur) => (cur === "saved" ? "none" : "saved"));
          }}
          title="Filter to references and saved items"
        >
          <i className="dot purple" />
          <span>Saved for later</span>
          <em>{savedForLaterCount}</em>
        </button>
        <button
          className={`smart-item-btn ${smartFilter === "today" ? "active" : ""}`}
          onClick={() => {
            setView("overview");
            setSmartFilter((cur) => (cur === "today" ? "none" : "today"));
          }}
          title="Filter to screenshots processed today"
        >
          <i className="dot green" />
          <span>Processed today</span>
          <em>{stats.processed_today}</em>
        </button>

        <div className="sidebar-bottom">
          <div
            className={`privacy-card ${
              config.ai_provider === "gemini"
                ? `cloud ${cloudStatus === "checking" ? "checking" : cloudStatus === "error" ? "error" : ""}`
                : config.ai_provider === "ollama"
                ? "neural"
                : "local"
            }`}
          >
            <strong>
              <i
                className={`status-dot ${
                  config.ai_provider === "gemini"
                    ? cloudStatus === "checking"
                      ? "yellow"
                      : cloudStatus === "error"
                      ? "red"
                      : ""
                    : ""
                }`}
              />{" "}
              {config.ai_provider === "gemini"
                ? cloudStatus === "checking"
                  ? "Checking Cloud AI…"
                  : cloudStatus === "error"
                  ? "Cloud AI (Offline)"
                  : cloudStatus === "connected"
                  ? "Cloud AI (Connected)"
                  : "Cloud AI (Gemini)"
                : config.ai_provider === "ollama"
                ? "Local Neural AI"
                : "Processing locally"}
            </strong>
            <p>
              {config.ai_provider === "gemini"
                ? cloudStatus === "checking"
                  ? "Testing connection to ScreenStash Cloud…"
                  : cloudStatus === "error"
                  ? "Service offline. Fallback heuristic engine active."
                  : "Connected to ScreenStash Cloud for vision analysis."
                : config.ai_provider === "ollama"
                ? `On-device reasoning via Ollama (${config.ollama_model}).`
                : "Your screenshots never leave this device."}
            </p>
            <button onClick={() => setView("settings")}>Manage setup →</button>
          </div>
          <NavButton active={view === "settings"} icon="⚙" label="Settings" onClick={() => setView("settings")} />
          <div className="profile">
            <div className="avatar">P</div>
            <div>
              <strong>Personal workspace</strong>
              <small>
                {config.ai_provider === "gemini"
                  ? cloudStatus === "connected"
                    ? "Cloud connected"
                    : cloudStatus === "checking"
                    ? "Checking cloud…"
                    : "Cloud offline (fallback)"
                  : "Local device"}
              </small>
            </div>
            <span>•••</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="breadcrumb">Workspace / {view[0].toUpperCase() + view.slice(1)}</p>
            <h1>
              {view === "settings"
                ? "Settings"
                : view === "calendar"
                ? "Monthly Calendar"
                : view === "tasks"
                ? "Active Tasks"
                : "Good morning, Piyush"}
            </h1>
          </div>
          <div className="top-actions">
            <div className="search-box-wrapper">
              <span className="search-icon">⌕</span>
              <input
                type="text"
                className="search-input"
                placeholder="Search with AI (e.g. 'urgent tasks', 'meeting with team', 'coffee receipts')…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  if (deepAiResults) setDeepAiResults(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") triggerDeepAiFilter();
                }}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => {
                    setSearchQuery("");
                    setDeepAiResults(null);
                  }}
                  title="Clear search"
                >
                  ×
                </button>
              )}
            </div>

            <button
              type="button"
              className={`ai-toggle-pill ${aiFilterActive ? "active" : ""}`}
              onClick={() => {
                if (searchQuery.trim() && !deepAiLoading) {
                  triggerDeepAiFilter();
                } else {
                  setAiFilterActive((prev) => !prev);
                }
              }}
              title={
                aiFilterActive
                  ? "AI Semantic filtering enabled. Click to run deep LLM reasoning."
                  : "Enable AI Semantic filtering"
              }
            >
              {deepAiLoading
                ? "✦ AI Analyzing…"
                : aiFilterActive
                ? deepAiResults
                  ? `✦ ${deepAiEngine}`
                  : "✦ AI Filter ON"
                : "✦ AI Filter OFF"}
            </button>
          </div>
        </header>

        {notice && (
          <div className="notice" onClick={() => setNotice("")}>
            {notice} <span>×</span>
          </div>
        )}

        {searchQuery.trim() && (
          <div className="search-results-chip">
            <span>
              Found <strong>{visibleItems.length}</strong> result{visibleItems.length === 1 ? "" : "s"} matching "
              {searchQuery}"{" "}
              {aiFilterActive && (
                <em style={{ marginLeft: 6, opacity: 0.85 }}>
                  (Filtered by {deepAiResults ? deepAiEngine : "AI Semantic Engine"})
                </em>
              )}
            </span>
            <button
              type="button"
              onClick={() => {
                setSearchQuery("");
                setDeepAiResults(null);
              }}
            >
              Clear search ×
            </button>
          </div>
        )}

        {smartFilter !== "none" && (
          <div className="active-filter-banner">
            <span>
              Showing AI collection:{" "}
              <strong>
                {smartFilter === "attention"
                  ? "Needs attention (AI Urgency & Tasks)"
                  : smartFilter === "saved"
                  ? "Saved for later (AI References & Receipts)"
                  : "Processed today"}
              </strong>{" "}
              ({visibleItems.length} items)
            </span>
            <button type="button" className="clear-filter-btn" onClick={() => setSmartFilter("none")}>
              Clear collection filter ×
            </button>
          </div>
        )}

        {view === "settings" ? (
          <Settings
            config={config}
            status={status}
            saving={saving}
            cloudStatus={cloudStatus}
            onCheckCloudConnection={checkCloudConnection}
            onChange={updateConfig}
            onSetupAi={handleSetupAi}
          />
        ) : view === "calendar" ? (
          <MonthlyCalendar items={visibleItems} onPreview={(item) => setLightboxItem(item)} />
        ) : (
          <Dashboard
            view={view}
            stats={stats}
            metrics={currentMetrics}
            items={visibleItems}
            aiReasons={itemAiReasons}
            status={status}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            onRefresh={refreshDashboard}
            onPreview={(item) => setLightboxItem(item)}
            onOpenFolder={openFileInFolder}
            onDelete={handleDeleteItem}
            onSearchSimilar={(q) => setSearchQuery(q)}
            onNotice={setNotice}
          />
        )}
      </main>

      {lightboxItem && (
        <LightboxModal
          item={lightboxItem}
          onClose={() => setLightboxItem(null)}
          onOpenFolder={openFileInFolder}
          onNotice={setNotice}
        />
      )}

      {onboarding && (
        <Onboarding config={config} setConfig={setConfig} onComplete={finishOnboarding} saving={saving} />
      )}
    </div>
  );
}

function NavButton({
  active,
  icon,
  label,
  badge,
  onClick
}: {
  active: boolean;
  icon: string;
  label: string;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button className={`nav-button ${active ? "active" : ""}`} onClick={onClick}>
      <span>
        <b>{icon}</b>
        {label}
      </span>
      {badge !== undefined && <em>{badge}</em>}
    </button>
  );
}

function TimeframeDropdown({
  selected,
  onChange
}: {
  selected: Timeframe;
  onChange: (t: Timeframe) => void;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [open]);

  return (
    <div className="timeframe-container">
      <button
        type="button"
        className="date-chip interactive"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
      >
        ◷ {TIMEFRAME_LABELS[selected]} ⌄
      </button>

      {open && (
        <div className="timeframe-dropdown" onClick={(e) => e.stopPropagation()}>
          {(Object.keys(TIMEFRAME_LABELS) as Timeframe[]).map((tf) => (
            <button
              key={tf}
              type="button"
              className={`timeframe-option ${selected === tf ? "active" : ""}`}
              onClick={() => {
                onChange(tf);
                setOpen(false);
              }}
            >
              <span>{TIMEFRAME_LABELS[tf]}</span>
              {selected === tf && <span className="check">✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Dashboard({
  view,
  stats,
  metrics,
  items,
  aiReasons,
  status,
  timeframe,
  onTimeframeChange,
  onRefresh,
  onPreview,
  onOpenFolder,
  onDelete,
  onSearchSimilar,
  onNotice
}: {
  view: string;
  stats: DashboardStats;
  metrics: { total: number; tasks: number; events: number; receipts: number };
  items: StashItem[];
  aiReasons: Record<string, string>;
  status: RuntimeStatus | null;
  timeframe: Timeframe;
  onTimeframeChange: (t: Timeframe) => void;
  onRefresh: () => void;
  onPreview: (item: StashItem) => void;
  onOpenFolder: (path: string) => void;
  onDelete: (item: StashItem) => void;
  onSearchSimilar: (q: string) => void;
  onNotice: (msg: string) => void;
}) {
  return (
    <>
      <section className="hero-row">
        <p className="muted">Here’s what your screenshots surfaced while you were away.</p>
        <TimeframeDropdown selected={timeframe} onChange={onTimeframeChange} />
      </section>

      <section className="metric-grid">
        <Metric label="Captured" value={metrics.total} delta={`${TIMEFRAME_LABELS[timeframe].toLowerCase()}`} />
        <Metric label="Tasks found" value={metrics.tasks} delta="from your stash" />
        <Metric label="Events" value={metrics.events} delta="from your stash" />
        <Metric label="Receipts" value={metrics.receipts} delta="from your stash" />
      </section>

      <section className="content-grid">
        <div className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RECENT ACTIVITY</p>
              <h2>{view === "calendar" ? "Upcoming from screenshots" : "Your latest stash"}</h2>
            </div>
            <button
              type="button"
              className="text-button"
              onClick={() => {
                onTimeframeChange("all");
                onNotice("Showing all historical screenshot records.");
              }}
            >
              View all ({items.length}) →
            </button>
          </div>

          {items.length ? (
            items.map((item, idx) => {
              const itemKey = `${item.title}-${item.time}`;
              return (
                <StashCard
                  key={`${item.title}-${item.time || idx}`}
                  item={item}
                  aiReason={aiReasons[itemKey]}
                  onPreview={onPreview}
                  onOpenFolder={onOpenFolder}
                  onDelete={onDelete}
                  onSearchSimilar={onSearchSimilar}
                  onNotice={onNotice}
                />
              );
            })
          ) : (
            <p className="muted empty-state">No screenshots match your current filter or timeframe.</p>
          )}
        </div>

        <div className="panel digest">
          <p className="eyebrow">LOCAL STATUS</p>
          <h2>A private workspace.</h2>
          <p className="muted">Your screenshot data stays in the local ScreenStash application directory.</p>
          <div className="progress">
            <span style={{ width: status?.service_running ? "100%" : "0%" }} />
          </div>
          <div className="digest-row">
            <span>Processing health</span>
            <strong>{status?.service_running ? "Active" : "Ready to start"}</strong>
          </div>
          <div className="digest-row">
            <span>Processed today</span>
            <strong>{stats.processed_today}</strong>
          </div>
          <div className="digest-row">
            <span>Active AI engine</span>
            <strong>{status?.model_ready ? "Gemma 3 (Neural)" : "Built-in Offline Engine"}</strong>
          </div>
          <button type="button" className="secondary-button" onClick={onRefresh}>
            Refresh status
          </button>
        </div>
      </section>
    </>
  );
}

function Metric({ label, value, delta }: { label: string; value: number; delta: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{delta}</small>
    </div>
  );
}

function StashCard({
  item,
  aiReason,
  onPreview,
  onOpenFolder,
  onDelete,
  onSearchSimilar,
  onNotice
}: {
  item: StashItem;
  aiReason?: string;
  onPreview: (item: StashItem) => void;
  onOpenFolder: (path: string) => void;
  onDelete: (item: StashItem) => void;
  onSearchSimilar: (q: string) => void;
  onNotice: (msg: string) => void;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [imgError, setImgError] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const assetUrl = useMemo(() => getScreenshotAssetUrl(item.file_path), [item.file_path]);
  const displaySrc = dataUrl || assetUrl;

  const handleImgError = useCallback(() => {
    if (!dataUrl && item.file_path) {
      loadScreenshotDataUrl(item.file_path).then((res) => {
        if (res) setDataUrl(res);
        else setImgError(true);
      });
    } else {
      setImgError(true);
    }
  }, [dataUrl, item.file_path]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menuOpen]);

  return (
    <article className="stash-card">
      {/* Thumbnail + Hover Preview */}
      <div
        className="stash-thumb-container"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => onPreview(item)}
        title="Click to expand screenshot"
      >
        {displaySrc && !imgError ? (
          <img
            src={displaySrc}
            alt={item.title}
            className="stash-thumb-img"
            onError={handleImgError}
          />
        ) : (
          <div className={`card-icon-placeholder ${item.accent}`}>
            {item.category === "Task" ? "✓" : item.category === "Event" ? "□" : item.category === "Receipt" ? "▤" : "✦"}
          </div>
        )}

        {/* Floating Hover Popover */}
        {hovered && displaySrc && !imgError && (
          <div className="stash-hover-popover" onClick={(e) => e.stopPropagation()}>
            <div className="hover-popover-preview">
              <img src={displaySrc} alt={item.title} className="hover-popover-img" />
            </div>
            <div className="hover-popover-info">
              <strong>{item.file_name || item.title}</strong>
              <small>Click to open ↗</small>
            </div>
          </div>
        )}
      </div>

      {/* Card Content Body */}
      <div className="card-body">
        <div className="card-title">
          <h3>{item.title}</h3>
          <span className={`tag ${item.accent}`}>{item.category}</span>
          {item.amount && <span className="cal-card-amount">{item.amount}</span>}
        </div>
        {aiReason && (
          <div className="ai-reason-pill">
            <span>✦ AI:</span> {aiReason}
          </div>
        )}
        <p>{item.summary}</p>
        {item.tasks && item.tasks.length > 0 && (
          <div className="cal-task-checklist" style={{ margin: "4px 0 6px" }}>
            <span className="cal-checklist-label">Tasks:</span>
            {item.tasks.slice(0, 2).map((t, idx) => (
              <span key={idx} style={{ fontSize: "11px", color: "#444" }}>
                • {t}
              </span>
            ))}
          </div>
        )}
        <small>{item.time}</small>
      </div>

      {/* Options Menu Button (•••) */}
      <div className="card-actions-wrapper">
        <button
          type="button"
          className={`more-btn ${menuOpen ? "active" : ""}`}
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((prev) => !prev);
          }}
          title="Screenshot options"
        >
          •••
        </button>

        {menuOpen && (
          <div className="card-dropdown-menu" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="menu-item"
              onClick={() => {
                setMenuOpen(false);
                onPreview(item);
              }}
            >
              View full screenshot
            </button>

            {item.file_path && (
              <button
                type="button"
                className="menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  onOpenFolder(item.file_path!);
                  onNotice(`Opened folder for ${item.file_name || item.title}`);
                }}
              >
                Show in folder
              </button>
            )}

            <button
              type="button"
              className="menu-item"
              onClick={() => {
                setMenuOpen(false);
                navigator.clipboard.writeText(item.summary || item.title);
                onNotice("Summary copied to clipboard!");
              }}
            >
              Copy summary
            </button>

            {item.raw_ocr_text && (
              <button
                type="button"
                className="menu-item"
                onClick={() => {
                  setMenuOpen(false);
                  navigator.clipboard.writeText(item.raw_ocr_text!);
                  onNotice("OCR text copied to clipboard!");
                }}
              >
                Copy OCR text
              </button>
            )}

            <button
              type="button"
              className="menu-item"
              onClick={() => {
                setMenuOpen(false);
                onSearchSimilar(item.title);
              }}
            >
              Search related
            </button>

            <button
              type="button"
              className="menu-item danger"
              onClick={() => {
                setMenuOpen(false);
                onDelete(item);
              }}
            >
              Remove from stash
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

function LightboxModal({
  item,
  onClose,
  onOpenFolder,
  onNotice
}: {
  item: StashItem;
  onClose: () => void;
  onOpenFolder: (path: string) => void;
  onNotice: (msg: string) => void;
}) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [imgFailed, setImgFailed] = useState(false);
  const assetUrl = useMemo(() => getScreenshotAssetUrl(item.file_path), [item.file_path]);

  useEffect(() => {
    let active = true;
    if (item.file_path) {
      loadScreenshotDataUrl(item.file_path).then((res) => {
        if (active && res) {
          setDataUrl(res);
        }
      });
    }
    return () => { active = false; };
  }, [item.file_path]);

  const displaySrc = dataUrl || assetUrl;

  const handleImgError = useCallback(() => {
    if (!dataUrl && item.file_path) {
      loadScreenshotDataUrl(item.file_path).then((res) => {
        if (res) setDataUrl(res);
        else setImgFailed(true);
      });
    } else {
      setImgFailed(true);
    }
  }, [dataUrl, item.file_path]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <div className="lightbox-modal" onClick={(e) => e.stopPropagation()}>
        <div className="lightbox-header">
          <div className="lightbox-header-info">
            <span className={`tag ${item.accent}`}>{item.category}</span>
            <h3>{item.title}</h3>
            {item.time && <small style={{ color: "#888" }}>{item.time.replace("T", " ").slice(0, 19)}</small>}
          </div>

          <div className="lightbox-header-actions">
            {item.file_path && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  onOpenFolder(item.file_path!);
                  onNotice(`Opened in Explorer: ${item.file_name || item.title}`);
                }}
              >
                Show in Folder
              </button>
            )}

            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                navigator.clipboard.writeText(item.summary || item.title);
                onNotice("Summary copied to clipboard!");
              }}
            >
              Copy Summary
            </button>

            <button type="button" className="icon-close-btn" onClick={onClose} title="Close (Esc)">
              ✕
            </button>
          </div>
        </div>

        <div className="lightbox-body">
          {displaySrc && !imgFailed ? (
            <img
              src={displaySrc}
              alt={item.title}
              className="lightbox-image"
              onError={handleImgError}
            />
          ) : (
            <div className="lightbox-fallback" style={{ textAlign: "center", padding: "40px 20px" }}>
              <div style={{ fontSize: "36px", marginBottom: "12px", opacity: 0.7 }}>🖼️</div>
              <p style={{ fontWeight: 600, fontSize: "15px", marginBottom: "6px", color: "#ddd" }}>Screenshot Preview Unavailable</p>
              <p style={{ color: "#888", fontSize: "12px", maxWidth: "420px", margin: "0 auto 16px" }}>
                The original screenshot file could not be displayed or was moved.
              </p>
              {item.file_path && (
                <div style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", padding: "6px 12px", borderRadius: "6px", display: "inline-block", maxWidth: "90%", wordBreak: "break-all", fontSize: "11px", color: "#aaa", marginBottom: "16px" }}>
                  {item.file_path}
                </div>
              )}
              {item.file_path && (
                <div>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      onOpenFolder(item.file_path!);
                      onNotice(`Opened in Explorer: ${item.file_name || item.title}`);
                    }}
                    style={{ margin: "0 auto" }}
                  >
                    Locate in File Explorer
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="lightbox-footer">
          <p className="lightbox-summary">{item.summary}</p>
          {item.tasks && item.tasks.length > 0 && (
            <div className="lightbox-tasks">
              <strong>Extracted Tasks:</strong>
              <ul>
                {item.tasks.map((t, idx) => (
                  <li key={idx}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          {item.raw_ocr_text && (
            <details style={{ marginTop: "8px", fontSize: "11px", color: "#777" }}>
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>Show Raw OCR Text</summary>
              <pre
                style={{
                  background: "#f4f3ed",
                  padding: "8px",
                  borderRadius: "6px",
                  whiteSpace: "pre-wrap",
                  marginTop: "4px"
                }}
              >
                {item.raw_ocr_text}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

function Settings({
  config,
  status,
  saving,
  cloudStatus,
  onCheckCloudConnection,
  onChange,
  onSetupAi
}: {
  config: AppConfig;
  status: RuntimeStatus | null;
  saving: boolean;
  cloudStatus: "checking" | "connected" | "error" | "idle";
  onCheckCloudConnection: () => void;
  onChange: (patch: Partial<AppConfig>) => void;
  onSetupAi: () => void;
}) {
  const isNeuralActive = Boolean(status?.model_ready);
  const isOllamaReadyToPull = Boolean(status?.ollama_available && !status?.model_ready);
  const isCloud = config.ai_provider === "gemini";
  const [folderInput, setFolderInput] = useState(config.screenshot_dir);

  useEffect(() => {
    setFolderInput(config.screenshot_dir);
  }, [config.screenshot_dir]);

  const isFolderDirty = folderInput.trim() !== config.screenshot_dir;
  const isFolderValid = folderInput.trim().length > 0;

  const handleApplyFolder = () => {
    const trimmed = folderInput.trim();
    if (trimmed && trimmed !== config.screenshot_dir) {
      onChange({ screenshot_dir: trimmed });
    }
  };

  return (
    <div className="settings-page">
      <div className="settings-intro">
        <p className="eyebrow">PREFERENCES</p>
        <h2>Make ScreenStash yours.</h2>
        <p className="muted">Everything is stored locally unless you explicitly select Cloud AI.</p>
      </div>
      <div className="settings-card">
        <div className="folder-field-container">
          <label className="field-label" htmlFor="screenshot-folder-input">
            Screenshot folder
          </label>
          <div className="folder-input-row">
            <input
              id="screenshot-folder-input"
              type="text"
              value={folderInput}
              placeholder="C:\Users\you\Pictures\Screenshots"
              onChange={(event) => setFolderInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && isFolderDirty && isFolderValid) {
                  event.preventDefault();
                  handleApplyFolder();
                }
              }}
            />
            <button
              type="button"
              className={`set-folder-btn ${isFolderDirty ? "dirty" : "clean"}`}
              disabled={saving || !isFolderDirty || !isFolderValid}
              onClick={handleApplyFolder}
            >
              {saving && isFolderDirty ? "Setting…" : isFolderDirty ? "Set folder" : "✓ Active"}
            </button>
          </div>
          <div className="folder-status-hint">
            {isFolderDirty ? (
              <span className="hint-dirty">
                ● Unsaved changes — click <strong>Set folder</strong> or press Enter to apply.
              </span>
            ) : (
              <span className="hint-active">✓ ScreenStash is actively watching this folder.</span>
            )}
          </div>
        </div>
        <SettingRow
          title="Watch for new screenshots"
          description="Only screenshots taken after ScreenStash starts watching are organized"
        >
          <Toggle
            value={config.auto_process_new_screenshots}
            onChange={(value) => onChange({ auto_process_new_screenshots: value })}
          />
        </SettingRow>
      </div>
      <div className="settings-card">
        <p className="eyebrow">INTELLIGENCE &amp; AI ENGINE</p>
        <div className="ai-section">
          <div className="ai-mode-header">
            <div className="ai-mode-header-text">
              <h3>Processing Mode</h3>
              <p>Choose how ScreenStash extracts tasks, dates, and summaries</p>
            </div>
            <select
              className="ai-select-styled"
              value={config.ai_provider}
              onChange={(event) => onChange({ ai_provider: event.target.value as AppConfig["ai_provider"] })}
            >
              <option value="offline">⚡ Built-in offline extraction</option>
              <option value="ollama">🧠 Local Ollama model</option>
              <option value="gemini">☁ Cloud AI — Gemini vision</option>
            </select>
          </div>

          {config.ai_provider === "offline" && (
            <div className="ai-card-box offline-theme">
              <div className="ai-badge-row">
                <span className="ai-pill offline">⚡ Fast On-Device Engine</span>
                <span className="ai-pill offline">🔒 100% Private &amp; Offline</span>
              </div>
              <p className="muted" style={{ margin: "2px 0 6px", color: "#475c35", fontWeight: 500 }}>
                Completely offline heuristic extraction with instant OCR. No accounts, model downloads, or network connections required.
              </p>
              <ul className="ai-points-list">
                <li>
                  <strong>Zero Network Requests:</strong> Screenshots are analyzed in memory and never leave this machine.
                </li>
                <li>
                  <strong>Instant Performance:</strong> Categorization, dates, checklist tasks, and currency extraction complete in &lt;50ms.
                </li>
                <li>
                  <strong>Zero System Bloat:</strong> 0 MB model download; runs smoothly on standard CPU without GPU requirements.
                </li>
              </ul>
            </div>
          )}

          {config.ai_provider === "ollama" && (
            <div className="ai-card-box neural-theme">
              <div className="ai-badge-row">
                <span className="ai-pill neural">🧠 Local Neural LLM</span>
                <span className="ai-pill neural">{isNeuralActive ? "🟢 Model Active" : "🟡 Setup Required"}</span>
              </div>
              <div className="model-row" style={{ padding: "4px 0" }}>
                <div className="model-orb">✦</div>
                <div>
                  <h3>{isNeuralActive ? `Neural LLM (${config.ollama_model})` : "Local model"}</h3>
                  <p className="muted">
                    {isOllamaReadyToPull
                      ? "Ollama detected on PC. Click below to pull model weights."
                      : "Install Ollama, then download a model for local reasoning."}
                  </p>
                </div>
                <select
                  className="ai-select-styled"
                  value={config.ollama_model}
                  onChange={(event) => onChange({ ollama_model: event.target.value })}
                >
                  <option value="gemma3:4b">Gemma 3 · recommended</option>
                  <option value="llama3.2:3b">Llama 3.2</option>
                </select>
              </div>
              {isOllamaReadyToPull && (
                <button
                  type="button"
                  className="primary-button"
                  style={{ alignSelf: "flex-start" }}
                  onClick={onSetupAi}
                >
                  ⬇ Download {config.ollama_model} via Ollama
                </button>
              )}
              {!status?.ollama_available && (
                <p className="muted" style={{ margin: 0 }}>
                  Install{" "}
                  <a
                    href="https://ollama.com/download"
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#7c3aed", fontWeight: 600 }}
                  >
                    Ollama
                  </a>{" "}
                  first. All processing remains on this device.
                </p>
              )}
              <label className="field-label" style={{ marginTop: 4 }}>
                Local Ollama endpoint
                <input
                  value={config.ollama_url}
                  onChange={(event) => onChange({ ollama_url: event.target.value })}
                />
              </label>
            </div>
          )}

          {isCloud && (
            <div className="ai-card-box cloud-theme">
              <div className="ai-badge-row">
                <span className="ai-pill cloud">☁ Gemini 2.0 Flash Vision</span>
                <span className="ai-pill quota">✨ 50 free extractions / mo</span>
              </div>

              <div
                className={`ai-status-banner ${
                  cloudStatus === "connected"
                    ? "connected"
                    : cloudStatus === "checking"
                    ? "checking"
                    : "error"
                }`}
              >
                <div className="ai-status-banner-left">
                  <i
                    className={`status-dot ${
                      cloudStatus === "connected" ? "" : cloudStatus === "checking" ? "yellow" : "red"
                    }`}
                  />
                  <span>
                    {cloudStatus === "checking" && "Connecting… Testing ScreenStash Cloud connection"}
                    {cloudStatus === "connected" && "Connected to ScreenStash Cloud (Ready)"}
                    {cloudStatus === "error" && "Cloud Service Offline — Fallback Active"}
                    {cloudStatus === "idle" && "Cloud AI Selected"}
                  </span>
                </div>
                <button
                  type="button"
                  className="retry-link"
                  onClick={onCheckCloudConnection}
                  disabled={cloudStatus === "checking"}
                >
                  {cloudStatus === "checking" ? "Testing…" : "Check again"}
                </button>
              </div>

              <div className="ai-consent-card">
                <label className="ai-consent-row">
                  <input
                    type="checkbox"
                    checked={config.cloud_consent}
                    onChange={(event) => onChange({ cloud_consent: event.target.checked })}
                  />
                  <span className="ai-consent-text">
                    I agree to send screenshots to ScreenStash Cloud &amp; Gemini for multimodal analysis.
                  </span>
                </label>
                <ul className="ai-points-list">
                  <li>
                    <strong>Zero Storage Guarantee:</strong> Images are processed in-memory and discarded immediately after extraction.
                  </li>
                  <li>
                    <strong>Monthly Plan:</strong> Includes 50 cloud vision extractions per month with zero local GPU overhead.
                  </li>
                </ul>
              </div>

              <div className="ai-fallback-callout">
                <span>⚡</span>
                <span>
                  <strong>Automatic Fallback:</strong> If offline, quota-limited, or network unavailable, ScreenStash automatically uses the built-in offline engine.
                </span>
              </div>
            </div>
          )}
        </div>
        <div className="settings-footer">
          <span>{saving ? "Saving…" : "Changes save automatically"}</span>
          <span className="privacy-pill">
            {isCloud ? "☁ Cloud processing enabled" : "🔒 Local-only processing"}
          </span>
        </div>
      </div>
    </div>
  );
}

function SettingRow({
  title,
  description,
  children
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="setting-row">
      <div>
        <h3>{title}</h3>
        <p className="muted">{description}</p>
      </div>
      {children}
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (value: boolean) => void }) {
  return (
    <button className={`toggle ${value ? "on" : ""}`} onClick={() => onChange(!value)} aria-label="Toggle setting">
      <span />
    </button>
  );
}

function Onboarding({
  config,
  setConfig,
  onComplete,
  saving
}: {
  config: AppConfig;
  setConfig: (config: AppConfig) => void;
  onComplete: () => void;
  saving: boolean;
}) {
  const [step, setStep] = useState(0);
  const steps = [
    {
      kicker: "WELCOME TO YOUR SECOND BRAIN",
      title: "Your screenshots, finally useful.",
      body: "ScreenStash turns the screenshots you already take into an organized, searchable workspace — privately, on this device.",
      icon: "✦"
    },
    {
      kicker: "CHOOSE YOUR WATCH FOLDER",
      title: "We’ll watch for screenshots here.",
      body: "The default folder was detected from your system. You can change it later in Settings.",
      icon: "⌑"
    },
    {
      kicker: "LOCAL AI, BY DEFAULT",
      title: "Private processing is the point.",
      body: "OCR and an offline heuristic engine work without an account. Add Ollama later for richer local summaries.",
      icon: "⌁"
    }
  ];
  const current = steps[step];
  return (
    <div className="onboarding-backdrop">
      <div className="onboarding">
        <div className="onboarding-art">
          <div className="big-orb">{current.icon}</div>
          <div className="art-line line-one" />
          <div className="art-line line-two" />
          <span className="art-caption">
            LOCAL-FIRST
            <br />
            BY DESIGN
          </span>
        </div>
        <div className="onboarding-copy">
          <div className="step-count">
            0{step + 1} <span>/ 03</span>
          </div>
          <p className="eyebrow">{current.kicker}</p>
          <h2>{current.title}</h2>
          <p>{current.body}</p>
          {step === 1 && (
            <label className="field-label">
              Screenshot directory
              <input
                value={config.screenshot_dir}
                onChange={(event) => setConfig({ ...config, screenshot_dir: event.target.value })}
              />
            </label>
          )}
          {step === 2 && (
            <label className="consent-row">
              <input
                type="checkbox"
                checked={config.process_locally}
                onChange={(event) => setConfig({ ...config, process_locally: event.target.checked })}
              />{" "}
              I understand screenshots may contain private information and will be processed locally.
            </label>
          )}
          <div className="onboarding-footer">
            <div className="step-dots">
              {steps.map((_, index) => (
                <i className={index === step ? "selected" : ""} key={index} />
              ))}
            </div>
            <button
              type="button"
              className="primary-button"
              disabled={saving || (step === 2 && !config.process_locally)}
              onClick={() => (step < 2 ? setStep(step + 1) : onComplete())}
            >
              {step < 2 ? "Continue →" : saving ? "Starting…" : "Start using ScreenStash →"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
