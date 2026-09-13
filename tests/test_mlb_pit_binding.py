from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sportsedge.mlb_pit_binding import MLBPITBindingError, bind_v8_game_sources


class MLBPITBindingTest(unittest.TestCase):
    def _fixture(self, root: Path, *, observed_at="2026-09-13T17:30:00+00:00"):
        schedule_raw = (json.dumps({
            "dates": [{"games": [{"gamePk": 777001, "teams": {
                "away": {"probablePitcher": {"id": 101}},
                "home": {"probablePitcher": {"id": 202}},
            }}]}],
        }, separators=(", ", ": ")) + "\n").encode()
        boxscore_raw = ("  " + json.dumps({
            "teams": {
                "away": {"players": {"ID11": {"person": {"id": 11}, "battingOrder": "100"}}},
                "home": {"players": {"ID22": {"person": {"id": 22}, "battingOrder": "100"}}},
            }
        }, separators=(",", ":")) + "\n").encode()
        schedule = root / "schedule.json"
        boxscore = root / "boxscore.json"
        schedule.write_bytes(schedule_raw)
        boxscore.write_bytes(boxscore_raw)
        manifest = {
            "schema": "MLB_SAME_FETCH_PIT_SOURCE_CAPTURE_V1",
            "capture_semantics": "SAME_RESPONSE_BYTES_CONSUMED_BY_MODEL",
            "promotion_authority": False,
            "retroactive_point_in_time_claim": False,
            "records": [
                {
                    "source_kind": "MLB_STATSAPI_SCHEDULE",
                    "path": str(schedule),
                    "sha256": hashlib.sha256(schedule_raw).hexdigest(),
                    "observed_at_utc": observed_at,
                },
                {
                    "source_kind": "MLB_STATSAPI_BOXSCORE",
                    "game_pk": 777001,
                    "path": str(boxscore),
                    "sha256": hashlib.sha256(boxscore_raw).hexdigest(),
                    "observed_at_utc": observed_at,
                },
            ],
        }
        return {"pit_source_capture": manifest}, schedule, boxscore

    def test_valid_same_fetch_sources_bind(self):
        with tempfile.TemporaryDirectory() as td:
            card, _, _ = self._fixture(Path(td))
            bound = bind_v8_game_sources(
                card,
                game_id="777001",
                captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
            )
            self.assertEqual("SAME_RESPONSE_BYTES_CONSUMED_BY_MODEL", bound["pit_capture_semantics"])
            self.assertFalse(bound["pit_binding_promotion_authority"])
            self.assertFalse(bound["pit_binding_retroactive_claim"])
            self.assertEqual(64, len(bound["starter_snapshot_sha256"]))
            self.assertEqual(64, len(bound["lineup_snapshot_sha256"]))

    def test_missing_manifest_blocks(self):
        with self.assertRaisesRegex(MLBPITBindingError, "MANIFEST_MISSING"):
            bind_v8_game_sources(
                {}, game_id="777001",
                captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
            )

    def test_hash_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            card, _, boxscore = self._fixture(Path(td))
            boxscore.write_bytes(boxscore.read_bytes() + b" ")
            with self.assertRaisesRegex(MLBPITBindingError, "SHA256_MISMATCH"):
                bind_v8_game_sources(
                    card, game_id="777001",
                    captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
                )

    def test_post_decision_observation_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            card, _, _ = self._fixture(Path(td), observed_at="2026-09-13T17:32:00+00:00")
            with self.assertRaisesRegex(MLBPITBindingError, "OBSERVED_AFTER_DECISION"):
                bind_v8_game_sources(
                    card, game_id="777001",
                    captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
                )

    def test_duplicate_schedule_source_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            card, _, _ = self._fixture(Path(td))
            card["pit_source_capture"]["records"].append(
                dict(card["pit_source_capture"]["records"][0])
            )
            with self.assertRaisesRegex(MLBPITBindingError, "STARTER_SOURCE_AMBIGUOUS"):
                bind_v8_game_sources(
                    card, game_id="777001",
                    captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
                )

    def test_schedule_without_target_game_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            card, schedule, _ = self._fixture(Path(td))
            replacement = b'{"dates":[{"games":[{"gamePk":999999}]}]}'
            schedule.write_bytes(replacement)
            card["pit_source_capture"]["records"][0]["sha256"] = hashlib.sha256(replacement).hexdigest()
            with self.assertRaisesRegex(MLBPITBindingError, "STARTER_SOURCE_AMBIGUOUS_OR_MISSING:0"):
                bind_v8_game_sources(
                    card, game_id="777001",
                    captured_at=datetime(2026, 9, 13, 17, 31, tzinfo=timezone.utc),
                )


if __name__ == "__main__":
    unittest.main()
