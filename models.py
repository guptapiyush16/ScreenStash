"""
Data models and schemas for ScreenStash.
Defines the structured representation of screenshots, extraction results,
tasks, and categories.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Category(str, Enum):
    TASK = "Task"
    EVENT = "Event"
    RECEIPT = "Receipt"
    REFERENCE = "Reference"
    OTHER = "Other"


class ProcessStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class ExtractionResult(BaseModel):
    """Structured fields returned by the AI & OCR pipeline."""
    title: str = Field(default="Untitled Screenshot", description="Short concise title summarizing the screenshot content")
    category: Category = Field(default=Category.REFERENCE, description="Broad category: Task, Event, Receipt, Reference, Other")
    summary: str = Field(default="", description="2-3 sentence summary explaining the content")
    dates: List[str] = Field(default_factory=list, description="Extracted dates, deadlines, or event times (e.g. YYYY-MM-DD or readable times)")
    tasks: List[str] = Field(default_factory=list, description="Actionable checklist items or to-dos extracted from the screenshot")
    amount: Optional[str] = Field(default=None, description="Monetary total or amount if this is a receipt or invoice")
    tags: List[str] = Field(default_factory=list, description="Keyword tags for easy filtering and search")
    raw_ocr_text: str = Field(default="", description="Complete OCR extracted raw text")
    confidence_score: float = Field(default=0.8, description="Estimated confidence of OCR and extraction (0.0 - 1.0)")


class ScreenshotRecord(BaseModel):
    """Database record representation of a tracked screenshot."""
    id: Optional[int] = None
    file_path: str
    file_name: str
    file_hash: str
    file_size_bytes: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    processed_at: Optional[str] = None
    status: ProcessStatus = ProcessStatus.PENDING
    error_message: Optional[str] = None
    
    # Extraction fields
    title: str = "Untitled Screenshot"
    category: str = Category.REFERENCE.value
    summary: str = ""
    dates_json: str = "[]"
    tasks_json: str = "[]"
    amount: Optional[str] = None
    tags_json: str = "[]"
    raw_ocr_text: str = ""
    confidence_score: float = 0.0

    @property
    def dates_list(self) -> List[str]:
        import json
        try:
            return json.loads(self.dates_json) if self.dates_json else []
        except Exception:
            return []

    @property
    def tasks_list(self) -> List[str]:
        import json
        try:
            return json.loads(self.tasks_json) if self.tasks_json else []
        except Exception:
            return []

    @property
    def tags_list(self) -> List[str]:
        import json
        try:
            return json.loads(self.tags_json) if self.tags_json else []
        except Exception:
            return []
