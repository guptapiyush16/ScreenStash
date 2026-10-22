"""
Unit and integration tests for ScreenStash.
Tests database persistence, deduplication, models, and heuristic extraction.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from models import Category, ProcessStatus, ExtractionResult, ScreenshotRecord
import database as db
import processor


class TestScreenStashPipeline(unittest.TestCase):

    def setUp(self):
        # Use a temporary SQLite database for test isolation
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = Path(self.temp_dir.name) / "test_screenstash.db"
        db.DATABASE_PATH = self.test_db_path
        db.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_initialization_and_crud(self):
        """Test database table creation, insertion, updating, and querying."""
        file_hash = "abc123hash"
        file_path = "C:/fake/screenshot1.png"
        
        # 1. Insert new record
        rec_id = db.insert_screenshot(
            file_path=file_path,
            file_name="screenshot1.png",
            file_hash=file_hash,
            file_size_bytes=1024
        )
        self.assertIsNotNone(rec_id)

        # 2. Duplicate insertion returns same id
        duplicate_id = db.insert_screenshot(
            file_path=file_path,
            file_name="screenshot1.png",
            file_hash=file_hash,
            file_size_bytes=1024
        )
        self.assertEqual(rec_id, duplicate_id)

        # 3. Retrieve record by hash
        record = db.get_screenshot_by_hash(file_hash)
        self.assertIsNotNone(record)
        self.assertEqual(record.file_name, "screenshot1.png")
        self.assertEqual(record.status, ProcessStatus.PENDING)

        # 4. Update extraction result
        ext = ExtractionResult(
            title="Design Review Notes",
            category=Category.TASK,
            summary="Review redesign for Q4 product launch",
            dates=["2026-10-25"],
            tasks=["Finalize navigation bar", "Export SVG icons"],
            tags=["design", "q4"],
            raw_ocr_text="Review redesign for Q4. Tasks: - Finalize navigation bar - Export SVG icons",
            confidence_score=0.95
        )
        db.update_extraction_result(rec_id, ext)

        updated_rec = db.get_screenshot_by_id(rec_id)
        self.assertEqual(updated_rec.status, ProcessStatus.PROCESSED)
        self.assertEqual(updated_rec.title, "Design Review Notes")
        self.assertEqual(updated_rec.category, Category.TASK.value)
        self.assertEqual(len(updated_rec.tasks_list), 2)
        self.assertIn("Finalize navigation bar", updated_rec.tasks_list)
        self.assertEqual(updated_rec.dates_list, ["2026-10-25"])

        # 5. Search query filtering
        search_res = db.get_all_screenshots(search_query="navigation")
        self.assertEqual(len(search_res), 1)

        empty_res = db.get_all_screenshots(search_query="nonexistent_keyword")
        self.assertEqual(len(empty_res), 0)

        # 6. Delete record
        deleted = db.delete_screenshot(rec_id)
        self.assertTrue(deleted)
        self.assertIsNone(db.get_screenshot_by_id(rec_id))

    def test_heuristic_fallback_task_detection(self):
        """Test heuristic AI when given task text."""
        raw_text = """
Sprint Planning Meeting
TODO:
- Deploy backend service
- Update database schema migration
Deadline: 2026-11-01
        """
        result = processor.fallback_heuristic_ai(raw_text, "sprint_task.png")
        self.assertEqual(result.category, Category.TASK)
        self.assertIn("Deploy backend service", result.tasks)
        self.assertTrue(any("2026-11-01" in d for d in result.dates))

    def test_heuristic_fallback_receipt_detection(self):
        """Test heuristic AI when given receipt text."""
        raw_text = """
COFFEE SHOP INC
Receipt #98234
1x Latte $4.50
1x Croissant $3.75
Subtotal: $8.25
Tax: $0.74
Total: $8.99
Paid with Visa
        """
        result = processor.fallback_heuristic_ai(raw_text, "coffee_receipt.png")
        self.assertEqual(result.category, Category.RECEIPT)
        self.assertIsNotNone(result.amount)
        self.assertIn("$", result.amount)

    def test_heuristic_fallback_event_detection(self):
        """Test heuristic AI when given calendar/meeting text."""
        raw_text = """
Product All-Hands Meeting
Join Zoom Meeting: https://zoom.us/j/12345
Date: Friday, Oct 24, 2026 at 3:00 PM
Agenda: Roadmap and Q&A
        """
        result = processor.fallback_heuristic_ai(raw_text, "zoom_invite.png")
        self.assertEqual(result.category, Category.EVENT)
        self.assertTrue(len(result.dates) > 0)


if __name__ == "__main__":
    unittest.main()
