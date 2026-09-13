import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import capture_closing_line_archive_v3 as v3

UTC = timezone.utc


class ClosingLineArchiveV3Tests(unittest.TestCase):
    def test_paid_fetch_persists_raw_payload_and_binds_rows(self):
        now = datetime(2026, 9, 18, 23, 0, tzinfo=UTC)
        event = {
            "id": "cfb-1",
            "commence_time": "2026-09-19T00:00:00Z",
            "home_team": "Home State",
            "away_team": "Away Tech",
        }
        odds = [{
            **event,
            "bookmakers": [{
                "key": "draftkings",
                "last_update": "2026-09-18T22:59:55Z",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Home State", "price": -120},
                        {"name": "Away Tech", "price": 105},
                    ],
                }],
            }],
        }]
        policy = {
            "policy_id": "CLOSING_LINE_ARCHIVE_V1",
            "sports": {"CFB": "americanfootball_ncaaf"},
            "books": ["draftkings"],
            "markets": ["h2h"],
            "regions": "us",
            "odds_format": "american",
            "windows": {
                "decision": {"min_minutes_before_start": 45, "max_minutes_before_start": 120},
                "close": {"min_minutes_before_start": 2, "max_minutes_before_start": 20},
                "t0_prestart": {"min_minutes_before_start": 0, "max_minutes_before_start": 5},
            },
            "persistence": {
                "path_template": "archive/closing-lines/{sport_key}/{date}.ndjson",
            },
        }
        with tempfile.TemporaryDirectory() as td, \
             patch.object(v3.v1, "fetch_event_index", return_value=[event]), \
             patch.object(v3.v1, "fetch_odds", return_value=odds):
            root = Path(td)
            report = v3.run(now=now, policy=policy, out_dir=root, keys=["x"], opener=None)
            self.assertEqual(report["total_rows_written"], 2)
            raw_rel = report["sports"]["CFB"]["raw_payload_path"]
            raw_path = root / raw_rel
            self.assertTrue(raw_path.is_file())
            self.assertEqual(raw_path.read_bytes(), v3.canonical_payload_bytes(odds))
            rows_path = root / "archive/closing-lines/americanfootball_ncaaf/2026-09-19.ndjson"
            rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertTrue(row["raw_payload_preserved"])
                self.assertEqual(row["fetch_payload_path"], raw_rel)
                self.assertEqual(row["fetch_payload_sha256"], row["fetch_sha256"])

    def test_existing_raw_hash_collision_fails_closed(self):
        payload = [{"id": "x"}]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rel, _ = v3.persist_raw_payload("americanfootball_ncaaf", payload, root)
            (root / rel).write_bytes(b"tampered")
            with self.assertRaisesRegex(Exception, "RAW_HASH_COLLISION"):
                v3.persist_raw_payload("americanfootball_ncaaf", payload, root)


if __name__ == "__main__":
    unittest.main()
