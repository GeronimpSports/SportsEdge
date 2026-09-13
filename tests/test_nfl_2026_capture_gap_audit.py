import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.audit_nfl_2026_capture_gaps import audit


class CaptureGapAuditTest(unittest.TestCase):
    def cfg(self, root):
        return {
            "timezone": "America/Chicago",
            "opener_weekday": "Tuesday",
            "opener_local_time": "09:00",
            "opener_window_minutes": 60,
            "week1_tuesday_local_date": "2026-09-01",
            "first_week": 2,
            "output_dir": str(Path(root) / "captures"),
        }

    def test_elapsed_missing_opener_writes_marker_not_capture(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = self.cfg(root)
            now = datetime(2026, 9, 12, 23, 0, tzinfo=ZoneInfo("America/Chicago"))
            written = audit(cfg, now)
            self.assertEqual(len(written), 1)
            marker = Path(root) / "captures/week02/opener_missed.json"
            opener = Path(root) / "captures/week02/opener.json"
            self.assertTrue(marker.is_file())
            self.assertFalse(opener.exists())
            data = json.loads(marker.read_text())
            self.assertEqual(data["status"], "MISSED_OR_BLOCKED")
            self.assertTrue(data["no_backfill"])
            self.assertEqual(data["reason"], "OPENER_WINDOW_ELAPSED_WITHOUT_CAPTURE")

    def test_existing_capture_prevents_marker(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = self.cfg(root)
            opener = Path(root) / "captures/week02/opener.json"
            opener.parent.mkdir(parents=True)
            opener.write_text("{}\n")
            now = datetime(2026, 9, 12, 23, 0, tzinfo=ZoneInfo("America/Chicago"))
            self.assertEqual(audit(cfg, now), [])
            self.assertFalse((opener.parent / "opener_missed.json").exists())

    def test_open_window_never_marks_missed(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = self.cfg(root)
            now = datetime(2026, 9, 8, 9, 30, tzinfo=ZoneInfo("America/Chicago"))
            self.assertEqual(audit(cfg, now), [])

    def test_marker_is_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = self.cfg(root)
            now = datetime(2026, 9, 12, 23, 0, tzinfo=ZoneInfo("America/Chicago"))
            audit(cfg, now)
            marker = Path(root) / "captures/week02/opener_missed.json"
            before = marker.read_bytes()
            later = datetime(2026, 9, 13, 1, 0, tzinfo=ZoneInfo("America/Chicago"))
            self.assertEqual(audit(cfg, later), [])
            self.assertEqual(marker.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
