"""ScreenStash's privacy-minimizing Gemini extraction API.

Deploy this module as a separate Render Web Service.  The Gemini secret lives
only in that service's environment; it is never sent to, or stored by, the
desktop application.
"""

import json
import logging
import os
import uuid
import base64
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from starlette.responses import JSONResponse

logger = logging.getLogger("screenstash.cloud_api")

MONTHLY_LIMIT = 50
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUESTS_PER_HOUR = 30
MAX_CONCURRENT_EXTRACTIONS = 2
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./screenstash_api.db")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")



class Base(DeclarativeBase):
    pass


class MonthlyUsage(Base):
    __tablename__ = "monthly_usage"
    __table_args__ = (UniqueConstraint("installation_id", "month", name="uq_usage_installation_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GeminiExtraction(BaseModel):
    title: str = Field(description="Descriptive title of the screenshot")
    category: str = Field(description="One of: Task, Event, Receipt, Reference, Other")
    summary: str = Field(description="1-2 sentence summary of screenshot content")
    dates: list[str] = Field(default_factory=list, description="Extracted dates, deadlines, or times")
    tasks: list[str] = Field(default_factory=list, description="Actionable checklist items or tasks")
    amount: str | None = Field(default=None, description="Monetary total with currency if a receipt or bill, else null")
    tags: list[str] = Field(default_factory=list, description="2-4 relevant keyword tags")


class ExtractionResponse(BaseModel):
    title: str
    category: str
    summary: str
    dates: list[str] = []
    tasks: list[str] = []
    amount: str | None = None
    tags: list[str] = []
    remaining: int



engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base.metadata.create_all(engine)
app = FastAPI(title="ScreenStash Cloud AI", docs_url=None, redoc_url=None)
_request_times: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()
_extraction_slots = threading.BoundedSemaphore(MAX_CONCURRENT_EXTRACTIONS)

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "category": {"type": "string", "enum": ["Task", "Event", "Receipt", "Reference", "Other"]},
        "summary": {"type": "string"},
        "dates": {"type": "array", "items": {"type": "string"}},
        "tasks": {"type": "array", "items": {"type": "string"}},
        "amount": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "category", "summary", "dates", "tasks", "amount", "tags"],
    "additionalProperties": False,
}


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def validated_installation_id(value: str | None) -> str:
    try:
        return str(uuid.UUID(value or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="A valid installation identifier is required") from exc


def client_address(request: Request) -> str:
    """Use the proxy-provided source address, falling back safely for local runs."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


def enforce_rate_limit(request: Request) -> None:
    now = time.monotonic()
    client = client_address(request)
    with _rate_lock:
        recent = _request_times[client]
        while recent and now - recent[0] >= 3600:
            recent.popleft()
        if len(recent) >= MAX_REQUESTS_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many extraction requests; try again later")
        recent.append(now)


def has_expected_image_signature(image_bytes: bytes, content_type: str | None) -> bool:
    """Reject arbitrary files disguised with an image MIME type."""
    signatures = {
        "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "image/webp": len(image_bytes) >= 12 and image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP",
        "image/bmp": image_bytes.startswith(b"BM"),
    }
    return signatures.get(content_type, False)


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    if request.url.path == "/v1/extractions":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_UPLOAD_BYTES + 16_384:
                    return JSONResponse(
                        {"detail": "Screenshots must be 10 MB or smaller"}, status_code=413
                    )
            except ValueError:
                return JSONResponse(
                    {"detail": "Invalid Content-Length"}, status_code=400
                )
    return await call_next(request)


@app.get("/")
@app.get("/health")
def health() -> dict[str, str | bool]:
    """Service and Gemini-readiness probe for Render and external uptime checks."""
    return {"status": "ok", "gemini_configured": bool(os.environ.get("GEMINI_API_KEY"))}


@app.post("/v1/extractions", response_model=ExtractionResponse)
def extract(request: Request, image: UploadFile = File(...), x_installation_id: str | None = Header(default=None)) -> ExtractionResponse:
    """Extract from an uploaded screenshot without persisting the image or its contents."""
    installation_id = validated_installation_id(x_installation_id)
    enforce_rate_limit(request)
    if image.content_type not in {"image/png", "image/jpeg", "image/webp", "image/bmp"}:
        raise HTTPException(status_code=415, detail="Supported image types are PNG, JPEG, WEBP, and BMP")
    image_bytes = image.file.read(MAX_UPLOAD_BYTES + 1)
    if not image_bytes or len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Screenshots must be 10 MB or smaller")
    if not has_expected_image_signature(image_bytes, image.content_type):
        raise HTTPException(status_code=415, detail="The uploaded file does not match its image type")
    month = current_month()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        usage = session.scalar(
            select(MonthlyUsage).where(MonthlyUsage.installation_id == installation_id, MonthlyUsage.month == month).with_for_update()
        )
        used = usage.count if usage else 0
        if used >= MONTHLY_LIMIT:
            raise HTTPException(status_code=429, detail="Monthly cloud extraction limit reached")

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=503, detail="Cloud AI is not configured")

        client = genai.Client(api_key=api_key)
        prompt = (
            "Analyze this screenshot and extract structured information.\n"
            "- Determine the primary category: Task, Event, Receipt, Reference, or Other.\n"
            "- Create a concise, descriptive title.\n"
            "- Write a 1-2 sentence summary of what this screenshot contains.\n"
            "- Extract actionable task items if present.\n"
            "- Extract any dates or deadlines if present.\n"
            "- Extract the full final total monetary amount with currency if this is a receipt, invoice, or bill (e.g. '$10.63').\n"

            "- Generate relevant tags.\n"
            f"Filename: {image.filename or 'screenshot'}"
        )
        if not _extraction_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Cloud AI is busy; try again shortly")
        try:
            candidate_models = [m for m in [GEMINI_MODEL, "gemini-2.0-flash", "gemini-1.5-flash"] if m]
            last_err = None
            response = None
            for model_name in candidate_models:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=image.content_type),
                            prompt,
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=GeminiExtraction,
                        ),
                    )
                    break
                except Exception as m_err:
                    last_err = m_err
                    logger.warning("Attempt with model %s failed: %s", model_name, m_err)
                    continue

            if response is None:
                raise last_err or RuntimeError("No candidate Gemini models succeeded")

            if hasattr(response, "parsed") and response.parsed:
                extracted = response.parsed.model_dump()
            else:
                raw_text = (response.text or "{}").strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                extracted = json.loads(raw_text.strip())

            cat = str(extracted.get("category", "Reference")).capitalize()
            if cat not in {"Task", "Event", "Receipt", "Reference", "Other"}:
                cat = "Reference"
            extracted["category"] = cat

            parsed = ExtractionResponse(**extracted, remaining=MONTHLY_LIMIT - used - 1)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Cloud extraction model call failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Cloud extraction failed: {type(exc).__name__} - {str(exc)}") from exc
        finally:
            _extraction_slots.release()

        if usage:
            usage.count += 1
            usage.updated_at = now
        else:
            session.add(MonthlyUsage(installation_id=installation_id, month=month, count=1, updated_at=now))
        session.commit()
        return parsed
