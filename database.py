"""
SQLite Database operations for ScreenStash.
Handles table creation, duplicate checks by file hash, indexing,
query filtering, full-text searches, and user modifications.
"""

import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from config import DATABASE_PATH
from models import ScreenshotRecord, ExtractionResult, ProcessStatus, Category

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection to the SQLite database with dictionary rows."""
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Initializes the database tables and indices if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            file_size_bytes INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            
            -- Extraction fields
            title TEXT DEFAULT 'Untitled Screenshot',
            category TEXT DEFAULT 'Reference',
            summary TEXT DEFAULT '',
            dates_json TEXT DEFAULT '[]',
            tasks_json TEXT DEFAULT '[]',
            amount TEXT,
            tags_json TEXT DEFAULT '[]',
            raw_ocr_text TEXT DEFAULT '',
            confidence_score REAL DEFAULT 0.0
        );
    """)

    # Indices for speed and search efficiency
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_hash ON screenshots(file_hash);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_category ON screenshots(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_status ON screenshots(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_created_at ON screenshots(created_at);")

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DATABASE_PATH}")


def insert_screenshot(
    file_path: str,
    file_name: str,
    file_hash: str,
    file_size_bytes: int = 0
) -> Optional[int]:
    """
    Inserts a newly detected screenshot with PENDING status.
    Returns the new row ID, or existing row ID if already present.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if duplicate already exists by hash
    cursor.execute("SELECT id FROM screenshots WHERE file_hash = ?", (file_hash,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    now = datetime.now().isoformat()
    try:
        cursor.execute("""
            INSERT INTO screenshots (
                file_path, file_name, file_hash, file_size_bytes, created_at, status
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (file_path, file_name, file_hash, file_size_bytes, now, ProcessStatus.PENDING.value))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return new_id
    except sqlite3.IntegrityError as e:
        conn.close()
        logger.warning(f"Screenshot already exists (integrity error): {file_path} - {e}")
        return None


def get_screenshot_by_hash(file_hash: str) -> Optional[ScreenshotRecord]:
    """Retrieve screenshot record by SHA256 file hash."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM screenshots WHERE file_hash = ?", (file_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return ScreenshotRecord(**dict(row))
    return None


def get_screenshot_by_id(record_id: int) -> Optional[ScreenshotRecord]:
    """Retrieve screenshot record by primary key."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM screenshots WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return ScreenshotRecord(**dict(row))
    return None


def update_status(record_id: int, status: ProcessStatus, error_message: Optional[str] = None) -> None:
    """Updates the status and error message of a screenshot."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE screenshots
        SET status = ?, error_message = ?
        WHERE id = ?
    """, (status.value, error_message, record_id))
    conn.commit()
    conn.close()


def update_extraction_result(record_id: int, result: ExtractionResult) -> None:
    """Updates the extraction output fields upon successful OCR and AI parsing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE screenshots
        SET 
            status = ?,
            processed_at = ?,
            title = ?,
            category = ?,
            summary = ?,
            dates_json = ?,
            tasks_json = ?,
            amount = ?,
            tags_json = ?,
            raw_ocr_text = ?,
            confidence_score = ?,
            error_message = NULL
        WHERE id = ?
    """, (
        ProcessStatus.PROCESSED.value,
        now,
        result.title,
        result.category.value,
        result.summary,
        json.dumps(result.dates, ensure_ascii=False),
        json.dumps(result.tasks, ensure_ascii=False),
        result.amount,
        json.dumps(result.tags, ensure_ascii=False),
        result.raw_ocr_text,
        result.confidence_score,
        record_id
    ))
    conn.commit()
    conn.close()


def update_user_edits(
    record_id: int,
    title: str,
    category: str,
    summary: str,
    tasks: List[str],
    dates: List[str],
    tags: List[str],
    amount: Optional[str] = None
) -> None:
    """Allows user to correct AI extraction fields from the dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE screenshots
        SET 
            title = ?,
            category = ?,
            summary = ?,
            tasks_json = ?,
            dates_json = ?,
            tags_json = ?,
            amount = ?
        WHERE id = ?
    """, (
        title,
        category,
        summary,
        json.dumps(tasks, ensure_ascii=False),
        json.dumps(dates, ensure_ascii=False),
        json.dumps(tags, ensure_ascii=False),
        amount,
        record_id
    ))
    conn.commit()
    conn.close()


def delete_screenshot(record_id: int) -> bool:
    """Removes a screenshot record from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM screenshots WHERE id = ?", (record_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_all_screenshots(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search_query: Optional[str] = None,
    order_by_desc: bool = True
) -> List[ScreenshotRecord]:
    """
    Fetches screenshots with optional filtering and full-text search across
    title, summary, tasks, tags, and raw OCR text.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM screenshots WHERE 1=1"
    params: List[Any] = []

    if category and category != "All":
        query += " AND category = ?"
        params.append(category)

    if status and status != "All":
        query += " AND status = ?"
        params.append(status)

    if search_query and search_query.strip():
        search_pattern = f"%{search_query.strip()}%"
        query += """ AND (
            title LIKE ? OR 
            summary LIKE ? OR 
            tasks_json LIKE ? OR 
            tags_json LIKE ? OR 
            raw_ocr_text LIKE ? OR
            file_name LIKE ?
        )"""
        params.extend([search_pattern] * 6)

    order_dir = "DESC" if order_by_desc else "ASC"
    query += f" ORDER BY created_at {order_dir}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [ScreenshotRecord(**dict(row)) for row in rows]


def get_stats() -> Dict[str, Any]:
    """Returns summary metrics for the dashboard counters."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM screenshots")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM screenshots WHERE status = 'PENDING'")
    pending = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM screenshots WHERE status = 'PROCESSED'")
    processed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM screenshots WHERE status = 'FAILED'")
    failed = cursor.fetchone()[0]

    # Category counts
    cursor.execute("""
        SELECT category, COUNT(*) as count 
        FROM screenshots 
        WHERE status = 'PROCESSED' 
        GROUP BY category
    """)
    category_counts = {row["category"]: row["count"] for row in cursor.fetchall()}

    conn.close()

    return {
        "total": total,
        "pending": pending,
        "processed": processed,
        "failed": failed,
        "categories": category_counts
    }
