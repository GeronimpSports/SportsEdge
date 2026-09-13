import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_mlb_v8_oddspapi_pit_v2 as v2


class ActualStartAttestationDiagnosticTests(unittest.TestCase):
    def _fixture(self, root: Path):
        fp = root / "2026-06-05" / "fixture-1" / "fixture.normalized.json"
        fp.parent.mkdir(parents=True)
        fixture = {"fixtureId": "fixture-1", "startTime": "2026-06-05T19:10:00Z"}
        fp.write_text(json.dumps(fixture), encoding="utf-8")
        return fp, fixture

    def test_missing_file_is_distinct_reason(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fp, fixture = self._fixture(root)
            att, reason = v2.attestation_diagnostic(root, fp, fixture)
            self.assertIsNone(att)
            self.assertEqual(reason, "MISSING_ATTESTATION_FILE")

    def test_fixture_sha_mismatch_is_distinct_reason(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fp, fixture = self._fixture(root)
            att_dir = root / "actual_starts"
            raw_dir = att_dir / "raw" / "fixture-1"
            raw_dir.mkdir(parents=True)
            schedule = raw_dir / "schedule.json"
            feed = raw_dir / "game_feed.json"
            schedule.write_text("{}", encoding="utf-8")
            feed.write_text("{}", encoding="utf-8")
            payload = {
                "schema": v2.ATT_SCHEMA,
                "source": "MLB_STATSAPI_GAME_FEED",
                "promotion_authority": False,
                "retroactive_point_in_time_claim": False,
                "fixture_id": "fixture-1",
                "fixture_sha256": "0" * 64,
                "schedule_payload_path": schedule.relative_to(root).as_posix(),
                "schedule_payload_sha256": v2.sha(schedule.read_bytes()),
                "game_feed_payload_path": feed.relative_to(root).as_posix(),
                "game_feed_payload_sha256": v2.sha(feed.read_bytes()),
                "actual_first_play_utc": "2026-06-05T19:11:00Z",
            }
            att_dir.mkdir(exist_ok=True)
            (att_dir / "fixture-1.json").write_text(json.dumps(payload), encoding="utf-8")
            att, reason = v2.attestation_diagnostic(root, fp, fixture)
            self.assertIsNone(att)
            self.assertEqual(reason, "ATTESTATION_FIXTURE_SHA_MISMATCH")


if __name__ == "__main__":
    unittest.main()
