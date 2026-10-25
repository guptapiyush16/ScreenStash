"""
Processing pipeline for ScreenStash.
Coordinates:
1. File write stabilization (ensures screenshot is completely written)
2. SHA-256 deduplication hashing
3. OCR text extraction via Tesseract (with graceful fallback)
4. AI structuring & classification via Ollama (with robust heuristic fallback)
5. Database updates
"""

import os
import re
import time
import json
import hashlib
import logging
import threading
import mimetypes
import uuid
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image

import requests
import pytesseract

from config import DEFAULT_CLOUD_API_URL, MAX_SCREENSHOT_BYTES, load_config
from ai_engine import is_local_ollama_url
from models import ExtractionResult, Category, ProcessStatus, ScreenshotRecord
import database as db
from notifier import show_saved_toast

logger = logging.getLogger(__name__)


def wait_for_file_settled(file_path: Path, check_interval: float = 0.5, max_wait: float = 5.0) -> bool:
    """
    Waits until the file write has stabilized by comparing file size over time.
    Prevents partial reads when OS is still writing the screenshot.
    """
    if not file_path.exists():
        return False

    elapsed = 0.0
    last_size = -1

    while elapsed < max_wait:
        try:
            current_size = file_path.stat().st_size
            if current_size > 0 and current_size == last_size:
                # File size is non-zero and unchanged
                return True
            last_size = current_size
        except (OSError, PermissionError):
            pass

        time.sleep(check_interval)
        elapsed += check_interval

    return file_path.exists() and file_path.stat().st_size > 0


def calculate_file_hash(file_path: Path) -> str:
    """Computes SHA-256 checksum of the screenshot file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_safe_image(file_path: Path) -> bool:
    """Validate image structure and dimensions before local OCR or cloud upload."""
    try:
        with Image.open(file_path) as image:
            width, height = image.size
            if width * height > 40_000_000:
                return False
            image.verify()
        return True
    except Exception:
        return False


def run_ocr(file_path: Path, tesseract_cmd: Optional[str] = None) -> Tuple[str, bool]:
    """
    Runs Tesseract OCR on the given image.
    Returns: (extracted_text, is_ocr_successful)
    """
    config = load_config()
    cmd = tesseract_cmd or config.get("tesseract_cmd")
    if cmd and os.path.exists(cmd):
        pytesseract.pytesseract.tesseract_cmd = cmd

    try:
        with Image.open(file_path) as img:
            # Reject decompression bombs before asking Pillow/Tesseract to decode pixels.
            width, height = img.size
            if width * height > 40_000_000:
                logger.warning("Skipping image with excessive dimensions: %s", file_path.name)
                return "", False
            # Convert to RGB if needed (e.g. RGBA or palette)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            text = pytesseract.image_to_string(img)
            return text.strip(), True
    except pytesseract.TesseractNotFoundError:
        logger.warning(f"Tesseract OCR executable not found at '{cmd}'. Falling back to metadata.")
        return "", False
    except Exception as e:
        logger.error(f"OCR processing failed for {file_path}: {e}")
        return "", False


def call_ollama_ai(ocr_text: str, file_name: str, config: Dict[str, Any]) -> Optional[ExtractionResult]:
    """
    Sends OCR text to Ollama /api/generate with strict JSON schema instructions.
    """
    ollama_url = config.get("ollama_url", "http://localhost:11434").rstrip("/")
    ollama_model = config.get("ollama_model", "gemma3:4b")
    if not is_local_ollama_url(ollama_url):
        logger.warning("Refusing non-local Ollama endpoint to protect screenshot privacy")
        return None

    system_prompt = (
        "You are an AI assistant that analyzes screenshots and OCR text. "
        "Your job is to extract actionable information, categorize the screenshot, "
        "and extract tasks, dates, amounts, and tags. "
        "You MUST return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "title": "Short descriptive title (max 7 words)",\n'
        '  "category": "Task" | "Event" | "Receipt" | "Reference" | "Other",\n'
        '  "summary": "2-3 concise sentences summarizing what this screenshot contains",\n'
        '  "dates": ["YYYY-MM-DD" or deadlines/time mentions],\n'
        '  "tasks": ["Actionable checklist item 1", "Actionable checklist item 2"],\n'
        '  "amount": "Total currency amount if receipt/invoice (e.g. $42.50 or null)",\n'
        '  "tags": ["tag1", "tag2"]\n'
        "}"
    )

    user_prompt = f"Filename: {file_name}\n\nOCR Extracted Text:\n{ocr_text[:3500]}"

    payload = {
        "model": ollama_model,
        "prompt": f"{system_prompt}\n\n{user_prompt}",
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    try:
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=20)
        if response.status_code == 200:
            data = response.json()
            raw_response = data.get("response", "{}")
            parsed = json.loads(raw_response)
            
            # Map category safely
            cat_str = parsed.get("category", "Reference").capitalize()
            category = Category.REFERENCE
            for cat in Category:
                if cat.value.lower() == cat_str.lower():
                    category = cat
                    break

            return ExtractionResult(
                title=parsed.get("title") or file_name,
                category=category,
                summary=parsed.get("summary") or "",
                dates=parsed.get("dates") or [],
                tasks=parsed.get("tasks") or [],
                amount=parsed.get("amount"),
                tags=parsed.get("tags") or [],
                raw_ocr_text=ocr_text,
                confidence_score=0.9
            )
    except Exception as e:
        logger.debug(f"Ollama call failed or timed out: {e}")

    return None


def call_gemini_cloud_ai(file_path: Path, config: Dict[str, Any]) -> Optional[ExtractionResult]:
    """Upload one screenshot to the consented ScreenStash cloud API; never persist it locally there."""
    api_url = str(config.get("cloud_api_url", "")).rstrip("/")
    parsed_url = urlparse(api_url)
    if (
        not config.get("cloud_consent")
        or api_url != DEFAULT_CLOUD_API_URL
        or parsed_url.scheme != "https"
        or parsed_url.netloc != "screenstash-cloudapi.onrender.com"
    ):
        logger.warning("Cloud AI was selected without valid HTTPS endpoint and consent")
        return None
    if file_path.stat().st_size > MAX_SCREENSHOT_BYTES:
        logger.warning("Skipping cloud extraction for oversized screenshot")
        return None
    installation_id = config.get("cloud_installation_id")
    try:
        uuid.UUID(str(installation_id))
    except (ValueError, TypeError):
        installation_id = str(uuid.uuid4())
        config["cloud_installation_id"] = installation_id
        from config import save_config
        save_config(config)
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if mime_type not in {"image/png", "image/jpeg", "image/webp", "image/bmp"}:
        return None
    try:
        with file_path.open("rb") as image:
            response = requests.post(
                f"{api_url}/v1/extractions",
                headers={"X-Installation-ID": str(installation_id)},
                files={"image": (file_path.name, image, mime_type)},
                timeout=60,
            )
        if response.status_code != 200:
            logger.warning("Cloud extraction unavailable (HTTP %s: %s); using offline fallback", response.status_code, response.text[:200])
            return None
        parsed = response.json()
        category = next((cat for cat in Category if cat.value.lower() == str(parsed.get("category", "")).lower()), Category.REFERENCE)
        return ExtractionResult(
            title=str(parsed.get("title") or file_path.name), category=category,
            summary=str(parsed.get("summary") or ""), dates=list(parsed.get("dates") or []),
            tasks=list(parsed.get("tasks") or []), amount=parsed.get("amount"),
            tags=list(parsed.get("tags") or []), raw_ocr_text="", confidence_score=0.9,
        )
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Cloud extraction failed; using offline fallback: %s", exc)
        return None



def fallback_heuristic_ai(ocr_text: str, file_name: str) -> ExtractionResult:
    """
    Intelligent heuristic fallback when Ollama is offline or image has minimal text.
    Extracts dates, currency, tasks, and infers categories using linguistic heuristics and regex.
    """
    clean_text = ocr_text.strip()
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

    # 1. Title inference
    title = file_name
    if lines:
        for line in lines:
            if 3 < len(line) < 60 and not re.match(r"^[\d\W]+$", line):
                title = line
                break

    # 2. Date extraction (ISO, US, EU, and month names)
    date_patterns = [
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",  # 2026-10-21
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",  # 10/21/2026
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:st|nd|rd|th)?,? \d{4}\b",
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b"
    ]
    found_dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, clean_text, re.IGNORECASE)
        for m in matches:
            if m not in found_dates:
                found_dates.append(m)

    # 3. Currency / Amount extraction
    amount_match = re.search(r"([$€£₹]\s?[\d,]+(?:\.\d{2})?|\b(?:USD|EUR|INR|CAD|GBP)\s*[\d,]+(?:\.\d{2})?)", clean_text)
    amount = amount_match.group(1).strip() if amount_match else None

    # 4. Category classification heuristics
    lower_text = clean_text.lower()
    category = Category.REFERENCE

    receipt_keywords = ["total", "subtotal", "tax", "invoice", "receipt", "paid", "order #", "payment", "visa", "mastercard"]
    event_keywords = ["zoom", "meeting", "google meet", "calendar", "webinar", "starts at", "pm", "am", "schedule", "rsvp"]
    task_keywords = ["todo", "to-do", "task", "fix", "bug", "feature", "deadline", "assigned", "action items", "github", "jira", "pr #"]

    receipt_score = sum(1 for kw in receipt_keywords if kw in lower_text)
    event_score = sum(1 for kw in event_keywords if kw in lower_text)
    task_score = sum(1 for kw in task_keywords if kw in lower_text)

    # 5. Task extraction
    extracted_tasks = []
    for line in lines:
        if re.search(r"^(\*|-|•|\[ \]|TODO:|\d+\.)\s+", line, re.I):
            task_item = re.sub(r"^(\*|-|•|\[ \]|TODO:|\d+\.)\s+", "", line).strip()
            if len(task_item) > 3 and task_item not in extracted_tasks:
                extracted_tasks.append(task_item)

    # 6. Categorization priority
    if amount or receipt_score >= 2:
        category = Category.RECEIPT
    elif (task_score > event_score) or (extracted_tasks and task_score >= 1) or any(re.search(r"(\[ \]|TODO|FIXME|action:)", l, re.I) for l in lines):
        category = Category.TASK
    elif event_score >= 2 or (found_dates and event_score >= 1):
        category = Category.EVENT
    elif extracted_tasks or task_score >= 1:
        category = Category.TASK

    # If no tasks explicitly formatted but is a Task category, pick actionable lines
    if not extracted_tasks and category == Category.TASK and lines:
        extracted_tasks = [lines[0]]

    # 6. Summary generation
    if lines:
        summary_lines = lines[:3]
        summary = ". ".join(summary_lines)
        if not summary.endswith("."):
            summary += "."
    else:
        summary = f"Screenshot image '{file_name}' captured with visual content."

    # 7. Tags
    tags = [category.value.lower()]
    if found_dates:
        tags.append("scheduled")
    if amount:
        tags.append("expense")
    if extracted_tasks:
        tags.append("action-item")

    return ExtractionResult(
        title=title,
        category=category,
        summary=summary,
        dates=found_dates[:5],
        tasks=extracted_tasks[:10],
        amount=amount,
        tags=tags,
        raw_ocr_text=clean_text,
        confidence_score=0.7 if clean_text else 0.4
    )


_IN_FLIGHT_FILES: set[str] = set()
_IN_FLIGHT_LOCK = threading.Lock()


def process_screenshot(file_path_str: str) -> Optional[ScreenshotRecord]:
    """
    Main processing pipeline entrypoint:
    1. Ensures write stability
    2. Calculates SHA-256 and detects duplicate
    3. Performs OCR
    4. Performs AI classification (Ollama with fallback)
    5. Saves result to SQLite
    """
    file_path = Path(file_path_str)
    if not file_path.exists():
        logger.error(f"File not found: {file_path_str}")
        return None

    resolved_path = str(file_path.resolve())
    with _IN_FLIGHT_LOCK:
        if resolved_path in _IN_FLIGHT_FILES:
            logger.info(f"File already in flight, skipping: {file_path.name}")
            return None
        _IN_FLIGHT_FILES.add(resolved_path)

    try:
        return _execute_processing(file_path)
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_FILES.discard(resolved_path)


def _execute_processing(file_path: Path) -> Optional[ScreenshotRecord]:
    record_id: Optional[int] = None
    # Process only ordinary image files from the watched folder. In particular,
    # never follow symlinks that could point at unrelated private files.
    if file_path.is_symlink() or not file_path.is_file():
        logger.warning("Skipping non-regular screenshot entry: %s", file_path.name)
        return None

    # Step 1: Wait for file write stabilization
    if not wait_for_file_settled(file_path):
        logger.warning(f"File {file_path.name} was not settled in time; it will be retried.")
        return None

    file_size = file_path.stat().st_size
    if file_size > MAX_SCREENSHOT_BYTES:
        logger.warning("Skipping oversized screenshot: %s", file_path.name)
        return None
    if not is_safe_image(file_path):
        logger.warning("Skipping invalid or unsafe image: %s", file_path.name)
        return None
    file_name = file_path.name

    # Step 2: Deduplication via SHA-256
    file_hash = calculate_file_hash(file_path)
    existing = db.get_screenshot_by_hash(file_hash)
    if existing and existing.status == ProcessStatus.PROCESSED:
        logger.info(f"Duplicate screenshot skipped (hash={file_hash[:8]}): {file_name}")
        return existing

    record_id = db.insert_screenshot(
        file_path=str(file_path.resolve()),
        file_name=file_name,
        file_hash=file_hash,
        file_size_bytes=file_size
    )

    if not record_id and existing:
        record_id = existing.id

    if not record_id:
        logger.error(f"Failed to record screenshot in database: {file_name}")
        return None

    try:
        db.update_status(record_id, ProcessStatus.PROCESSING)
        app_config = load_config()

        is_cloud = app_config.get("ai_provider") == "gemini" and app_config.get("cloud_consent")
        show_saved_toast(
            title="ScreenStash is analyzing",
            message="Analyzing with ScreenStash Cloud AI..." if is_cloud else "Processing locally. Your screenshot stays on this device.",
            category="Info",
            duration_ms=3000
        )


        extraction: Optional[ExtractionResult] = None
        raw_ocr = ""
        ocr_ok = False
        if app_config.get("ai_provider") == "gemini":
            extraction = call_gemini_cloud_ai(file_path, app_config)
        if not extraction:
            raw_ocr, ocr_ok = run_ocr(file_path, app_config.get("tesseract_cmd"))
        if not extraction and app_config.get("ai_provider") == "ollama" and raw_ocr.strip():
            extraction = call_ollama_ai(raw_ocr, file_name, app_config)
        if not extraction:
            extraction = fallback_heuristic_ai(raw_ocr, file_name)
        if not ocr_ok and app_config.get("ai_provider") != "gemini":
            extraction.confidence_score = min(extraction.confidence_score, 0.4)

        db.update_extraction_result(record_id, extraction)
        logger.info(f"Successfully processed screenshot #{record_id} ({file_name}) -> {extraction.category.value}")

        if app_config.get("notify_on_results", True):
            short_title = extraction.title
            if len(short_title) > 42:
                short_title = short_title[:39] + "..."
            show_saved_toast(
                title=f"{extraction.category.value} found in your screenshot",
                message=short_title or file_name,
                category=extraction.category.value,
                duration_ms=4000
            )
        return db.get_screenshot_by_id(record_id)
    except Exception as exc:
        if record_id is not None:
            db.update_status(record_id, ProcessStatus.FAILED, str(exc))
        logger.error("Screenshot processing failed for %s: %s", file_path, exc, exc_info=True)
        return None
