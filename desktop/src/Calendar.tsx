import { useMemo, useState } from "react";
import type { Category, StashItem } from "./types";

const DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"
];

function padZero(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function formatDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = padZero(date.getMonth() + 1);
  const d = padZero(date.getDate());
  return `${y}-${m}-${d}`;
}

function parseItemDates(item: StashItem): string[] {
  const dates = new Set<string>();

  // 1. Primary timestamp from capture
  if (item.time) {
    const match = item.time.match(/\d{4}-\d{2}-\d{2}/);
    if (match) dates.add(match[0]);
  }

  // 2. Explicit extracted dates array from AI/OCR if provided
  if (item.dates && Array.isArray(item.dates)) {
    for (const d of item.dates) {
      const match = d.match(/\d{4}-\d{2}-\d{2}/);
      if (match) {
        dates.add(match[0]);
      } else {
        // Weekday mapping relative to capture date if known
        const weekdays: { [key: string]: number } = {
          monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6, sunday: 0
        };
        const lower = d.toLowerCase();
        for (const [dayName, dayIndex] of Object.entries(weekdays)) {
          if (lower.includes(dayName)) {
            // Map to the capture week
            const base = item.time ? new Date(item.time) : new Date();
            if (!isNaN(base.getTime())) {
              const currentDay = base.getDay();
              const diff = (dayIndex - currentDay + 7) % 7;
              const target = new Date(base);
              target.setDate(base.getDate() + diff);
              dates.add(formatDateKey(target));
            }
          }
        }
      }
    }
  }

  // 3. Fallback: check if summary contains ISO dates
  if (item.summary) {
    const matches = item.summary.match(/\b\d{4}-\d{2}-\d{2}\b/g);
    if (matches) {
      matches.forEach((m) => dates.add(m));
    }
  }

  return Array.from(dates);
}

export function MonthlyCalendar({ items }: { items: StashItem[] }) {
  const today = useMemo(() => new Date(), []);
  const todayKey = useMemo(() => formatDateKey(today), [today]);

  const [currentYear, setCurrentYear] = useState<number>(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState<number>(today.getMonth());
  const [selectedDateKey, setSelectedDateKey] = useState<string>(todayKey);
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const [completedTasks, setCompletedTasks] = useState<Record<string, boolean>>({});

  // Map each dateKey (YYYY-MM-DD) to matching items
  const itemsByDate = useMemo(() => {
    const map = new Map<string, StashItem[]>();
    for (const item of items) {
      if (categoryFilter !== "All" && item.category !== categoryFilter) {
        continue;
      }
      const dateKeys = parseItemDates(item);
      if (dateKeys.length === 0) {
        // Default to today if unparseable
        const k = todayKey;
        const existing = map.get(k) || [];
        existing.push(item);
        map.set(k, existing);
      } else {
        for (const k of dateKeys) {
          const existing = map.get(k) || [];
          existing.push(item);
          map.set(k, existing);
        }
      }
    }
    return map;
  }, [items, categoryFilter, todayKey]);

  // Total items in current month
  const monthlyStats = useMemo(() => {
    let events = 0;
    let tasks = 0;
    let receipts = 0;
    let references = 0;
    const prefix = `${currentYear}-${padZero(currentMonth + 1)}`;

    for (const [dateKey, dayItems] of itemsByDate.entries()) {
      if (dateKey.startsWith(prefix)) {
        for (const item of dayItems) {
          if (item.category === "Event") events++;
          else if (item.category === "Task") tasks++;
          else if (item.category === "Receipt") receipts++;
          else references++;
        }
      }
    }
    return { events, tasks, receipts, references, total: events + tasks + receipts + references };
  }, [itemsByDate, currentYear, currentMonth]);

  // Navigate months
  function prevMonth() {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear((y) => y - 1);
    } else {
      setCurrentMonth((m) => m - 1);
    }
  }

  function nextMonth() {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear((y) => y + 1);
    } else {
      setCurrentMonth((m) => m + 1);
    }
  }

  function goToToday() {
    setCurrentYear(today.getFullYear());
    setCurrentMonth(today.getMonth());
    setSelectedDateKey(todayKey);
  }

  // Generate 35-42 grid cells
  const calendarCells = useMemo(() => {
    const firstDayOfMonth = new Date(currentYear, currentMonth, 1);
    // JS getDay(): 0 is Sunday, 1 is Monday... convert so 0 is Monday
    let startingDayOfWeek = firstDayOfMonth.getDay() - 1;
    if (startingDayOfWeek === -1) startingDayOfWeek = 6;

    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const daysInPrevMonth = new Date(currentYear, currentMonth, 0).getDate();

    interface CellData {
      dateKey: string;
      dayNumber: number;
      isCurrentMonth: boolean;
      isToday: boolean;
      isSelected: boolean;
      items: StashItem[];
    }

    const cells: CellData[] = [];

    // Leading days from previous month
    for (let i = startingDayOfWeek - 1; i >= 0; i--) {
      const day = daysInPrevMonth - i;
      const prevDate = new Date(currentYear, currentMonth - 1, day);
      const key = formatDateKey(prevDate);
      cells.push({
        dateKey: key,
        dayNumber: day,
        isCurrentMonth: false,
        isToday: key === todayKey,
        isSelected: key === selectedDateKey,
        items: itemsByDate.get(key) || []
      });
    }

    // Days in current month
    for (let day = 1; day <= daysInMonth; day++) {
      const curDate = new Date(currentYear, currentMonth, day);
      const key = formatDateKey(curDate);
      cells.push({
        dateKey: key,
        dayNumber: day,
        isCurrentMonth: true,
        isToday: key === todayKey,
        isSelected: key === selectedDateKey,
        items: itemsByDate.get(key) || []
      });
    }

    // Trailing days from next month to complete row of 7
    const remaining = (7 - (cells.length % 7)) % 7;
    for (let day = 1; day <= remaining; day++) {
      const nextDate = new Date(currentYear, currentMonth + 1, day);
      const key = formatDateKey(nextDate);
      cells.push({
        dateKey: key,
        dayNumber: day,
        isCurrentMonth: false,
        isToday: key === todayKey,
        isSelected: key === selectedDateKey,
        items: itemsByDate.get(key) || []
      });
    }

    return cells;
  }, [currentYear, currentMonth, todayKey, selectedDateKey, itemsByDate]);

  // Selected date items
  const selectedItems = useMemo(() => {
    return itemsByDate.get(selectedDateKey) || [];
  }, [itemsByDate, selectedDateKey]);

  // Format selected date for display
  const selectedDateLabel = useMemo(() => {
    const parts = selectedDateKey.split("-");
    if (parts.length === 3) {
      const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      return d.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric"
      });
    }
    return selectedDateKey;
  }, [selectedDateKey]);

  function toggleTask(taskId: string) {
    setCompletedTasks((prev) => ({
      ...prev,
      [taskId]: !prev[taskId]
    }));
  }

  return (
    <div className="calendar-view-container">
      {/* Top Controls Header */}
      <div className="cal-header-bar">
        <div className="cal-header-left">
          <h2 className="cal-title">
            {MONTH_NAMES[currentMonth]} <span className="cal-year">{currentYear}</span>
          </h2>
          <span className="cal-month-badge">
            {monthlyStats.total} screenshot{monthlyStats.total === 1 ? "" : "s"} in {MONTH_NAMES[currentMonth]}
          </span>
        </div>

        <div className="cal-header-center">
          <div className="cal-filter-pills">
            {["All", "Event", "Task", "Receipt", "Reference"].map((cat) => (
              <button
                key={cat}
                className={`cal-filter-btn ${categoryFilter === cat ? "active" : ""}`}
                onClick={() => setCategoryFilter(cat)}
              >
                {cat === "All" ? "All Items" : cat === "Event" ? "Events" : cat === "Task" ? "Tasks" : cat === "Receipt" ? "Receipts" : "References"}
              </button>
            ))}
          </div>
        </div>

        <div className="cal-header-right">
          <button className="cal-nav-btn" onClick={prevMonth} title="Previous Month">
            ‹
          </button>
          <button className="cal-today-btn" onClick={goToToday}>
            Today
          </button>
          <button className="cal-nav-btn" onClick={nextMonth} title="Next Month">
            ›
          </button>
        </div>
      </div>

      {/* Main Grid + Agenda Split Layout */}
      <div className="cal-layout-grid">
        {/* Monthly Calendar Grid */}
        <div className="cal-grid-panel">
          {/* Weekday Labels */}
          <div className="cal-weekdays-row">
            {DAYS_OF_WEEK.map((d) => (
              <div key={d} className="cal-weekday-label">
                {d}
              </div>
            ))}
          </div>

          {/* Days Grid */}
          <div className="cal-cells-grid">
            {calendarCells.map((cell) => {
              const hasEvents = cell.items.some((i) => i.category === "Event");
              const hasTasks = cell.items.some((i) => i.category === "Task");
              const hasReceipts = cell.items.some((i) => i.category === "Receipt");
              const hasRef = cell.items.some((i) => i.category === "Reference");

              return (
                <div
                  key={cell.dateKey}
                  className={`cal-cell ${!cell.isCurrentMonth ? "other-month" : ""} ${cell.isToday ? "is-today" : ""} ${cell.isSelected ? "is-selected" : ""} ${cell.items.length > 0 ? "has-items" : ""}`}
                  onClick={() => setSelectedDateKey(cell.dateKey)}
                >
                  <div className="cal-cell-header">
                    <span className={`cal-day-num ${cell.isToday ? "today-badge" : ""}`}>
                      {cell.dayNumber}
                    </span>
                    {cell.items.length > 0 && (
                      <span className="cal-item-count-badge">
                        {cell.items.length}
                      </span>
                    )}
                  </div>

                  {/* Item preview chips on cell */}
                  <div className="cal-cell-chips">
                    {cell.items.slice(0, 2).map((item, idx) => (
                      <div
                        key={idx}
                        className={`cal-mini-chip ${item.accent}`}
                        title={`${item.category}: ${item.title}`}
                      >
                        <span className="cal-chip-icon">
                          {item.category === "Event" ? "□" : item.category === "Task" ? "✓" : item.category === "Receipt" ? "▤" : "✦"}
                        </span>
                        <span className="cal-chip-text">{item.title}</span>
                      </div>
                    ))}
                    {cell.items.length > 2 && (
                      <div className="cal-more-chip">
                        +{cell.items.length - 2} more
                      </div>
                    )}
                  </div>

                  {/* Dot Indicators */}
                  {cell.items.length > 0 && (
                    <div className="cal-cell-dots">
                      {hasEvents && <i className="cal-dot purple" title="Events" />}
                      {hasTasks && <i className="cal-dot peach" title="Tasks" />}
                      {hasReceipts && <i className="cal-dot green" title="Receipts" />}
                      {hasRef && <i className="cal-dot lime" title="References" />}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Quick Monthly Summary Footer */}
          <div className="cal-grid-footer">
            <div className="cal-stat-chip purple">
              <i className="cal-dot purple" />
              <strong>{monthlyStats.events}</strong> Events
            </div>
            <div className="cal-stat-chip peach">
              <i className="cal-dot peach" />
              <strong>{monthlyStats.tasks}</strong> Tasks
            </div>
            <div className="cal-stat-chip green">
              <i className="cal-dot green" />
              <strong>{monthlyStats.receipts}</strong> Receipts
            </div>
            <div className="cal-stat-chip lime">
              <i className="cal-dot lime" />
              <strong>{monthlyStats.references}</strong> References
            </div>
          </div>
        </div>

        {/* Selected Day Agenda & Details Panel */}
        <aside className="cal-agenda-panel">
          <div className="cal-agenda-header">
            <div>
              <p className="eyebrow">DAY SCHEDULE</p>
              <h3>{selectedDateLabel}</h3>
            </div>
            <span className="cal-agenda-count">
              {selectedItems.length} {selectedItems.length === 1 ? "item" : "items"}
            </span>
          </div>

          <div className="cal-agenda-body">
            {selectedItems.length > 0 ? (
              <div className="cal-agenda-list">
                {selectedItems.map((item, index) => {
                  const itemKey = `${item.title}-${index}`;
                  return (
                    <article key={itemKey} className="cal-agenda-card">
                      <div className="cal-card-top">
                        <span className={`tag ${item.accent}`}>
                          {item.category === "Event" ? "□ Event" : item.category === "Task" ? "✓ Task" : item.category === "Receipt" ? "▤ Receipt" : "✦ Reference"}
                        </span>
                        {item.time && (
                          <span className="cal-time-hint">
                            {item.time.includes("T") ? item.time.split("T")[1].slice(0, 5) : item.time.slice(11, 16) || "Organized"}
                          </span>
                        )}
                      </div>

                      <h4 className="cal-card-title">{item.title}</h4>
                      <p className="cal-card-summary">{item.summary}</p>

                      {/* Display checklist if tasks found */}
                      {item.tasks && item.tasks.length > 0 && (
                        <div className="cal-task-checklist">
                          <p className="cal-checklist-label">Extracted Tasks:</p>
                          {item.tasks.map((task, tIdx) => {
                            const taskId = `${itemKey}-t-${tIdx}`;
                            const isDone = Boolean(completedTasks[taskId]);
                            return (
                              <label key={taskId} className={`cal-check-row ${isDone ? "completed" : ""}`}>
                                <input
                                  type="checkbox"
                                  checked={isDone}
                                  onChange={() => toggleTask(taskId)}
                                />
                                <span>{task}</span>
                              </label>
                            );
                          })}
                        </div>
                      )}

                      {/* Display extracted dates / deadlines if available */}
                      {item.dates && item.dates.length > 0 && (
                        <div className="cal-card-dates">
                          <span className="cal-date-tag">
                            📅 {item.dates.join(", ")}
                          </span>
                        </div>
                      )}

                      {/* Display amount if receipt */}
                      {item.amount && (
                        <div className="cal-card-amount">
                          <strong>Amount:</strong> {item.amount}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="cal-empty-agenda">
                <div className="cal-empty-icon">📅</div>
                <h4>No screenshots for this day</h4>
                <p>
                  Press <kbd>Win</kbd> + <kbd>Shift</kbd> + <kbd>S</kbd> to capture screenshots containing meetings, invites, or tasks. ScreenStash will automatically organize them here.
                </p>
                {selectedDateKey !== todayKey && (
                  <button className="secondary-button" onClick={goToToday}>
                    Jump to Today →
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
