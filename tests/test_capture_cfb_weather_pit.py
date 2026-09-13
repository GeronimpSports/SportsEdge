import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.capture_cfb_weather_pit import capture_weather

UTC = timezone.utc


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def read(self):
        return self._raw


class CFBWeatherCaptureTests(unittest.TestCase):
    def test_prestart_weather_is_hash_bound_and_append_only(self):
        now = datetime(2026, 9, 18, 23, 45, tzinfo=UTC)
        event = {
            "id": "401000001",
            "date": "2026-09-19T00:00:00Z",
            "competitions": [{
                "date": "2026-09-19T00:00:00Z",
                "status": {"type": {"state": "pre"}},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Home State"}},
                    {"homeAway": "away", "team": {"displayName": "Away Tech"}},
                ],
            }],
        }
        summary = {
            "header": {"competitions": [{
                "status": {"type": {"state": "pre"}},
                "weather": {"temperature": 72, "displayValue": "Clear"},
            }]}
        }
        def opener(url, timeout=20):
            if "summary?event=401000001" in url:
                return _Response(summary)
            if "dates=20260918" in url:
                return _Response({"events": [event]})
            if "dates=20260919" in url:
                return _Response({"events": []})
            raise AssertionError(url)

        policy = {
            "windows": {
                "t0_prestart": {"min_minutes_before_start": 0, "max_minutes_before_start": 5},
                "close": {"min_minutes_before_start": 2, "max_minutes_before_start": 20},
                "decision": {"min_minutes_before_start": 45, "max_minutes_before_start": 120},
            }
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = capture_weather(now=now, policy=policy, out_dir=root, opener=opener)
            self.assertEqual(report["observations_written"], 1)
            path = root / "history/cfb/weather/2026-09-19.ndjson"
            row = json.loads(path.read_text().strip())
            self.assertEqual(row["status_state"], "pre")
            self.assertTrue(row["prestart_attested"])
            self.assertEqual(row["window"], "close")
            self.assertEqual(row["weather"]["temperature"], 72)
            raw_path = root / row["raw_relative_path"]
            self.assertTrue(raw_path.is_file())
            import hashlib
            self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), row["raw_sha256"])
            self.assertFalse(row["promotion_authority"])

    def test_started_event_is_not_captured(self):
        now = datetime(2026, 9, 18, 23, 45, tzinfo=UTC)
        event = {
            "id": "401000002",
            "date": "2026-09-19T00:00:00Z",
            "competitions": [{
                "status": {"type": {"state": "in"}},
                "competitors": [],
            }],
        }
        def opener(url, timeout=20):
            if "scoreboard" in url:
                return _Response({"events": [event] if "20260918" in url else []})
            raise AssertionError("summary must not be fetched after start")
        policy = {"windows": {
            "close": {"min_minutes_before_start": 2, "max_minutes_before_start": 20},
            "t0_prestart": {"min_minutes_before_start": 0, "max_minutes_before_start": 5},
            "decision": {"min_minutes_before_start": 45, "max_minutes_before_start": 120},
        }}
        with tempfile.TemporaryDirectory() as td:
            report = capture_weather(now=now, policy=policy, out_dir=Path(td), opener=opener)
            self.assertEqual(report["observations_written"], 0)
            self.assertEqual(report["skips"][0]["reason"], "SCOREBOARD_NOT_PRESTART")


if __name__ == "__main__":
    unittest.main()
