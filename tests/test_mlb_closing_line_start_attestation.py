import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import attest_mlb_closing_line_starts as mod


class StartAttestationTests(unittest.TestCase):
    def test_attestation_is_non_promoting_and_source_bound(self):
        row = {"home_team": "Chicago Cubs", "away_team": "Milwaukee Brewers", "commence_time": "2026-09-12T18:20:00Z"}
        feed = {"liveData": {"plays": {"allPlays": [{"about": {"startTime": "2026-09-12T18:27:41Z"}}]}}}
        raw = json.dumps(feed).encode()
        with patch.object(mod, "_get", return_value=raw):
            att = mod._attest("provider-event", row, 12345)
        self.assertIsNotNone(att)
        self.assertEqual(att["event_id"], "provider-event")
        self.assertEqual(att["source_event_id"], "12345")
        self.assertEqual(att["evidence_class"], "NOT_EVIDENCE_ADJUDICATION_ONLY")
        self.assertFalse(att["promotion_authority"])
        self.assertFalse(att["retroactive_point_in_time_claim"])
        self.assertEqual(len(att["source_sha256"]), 64)

    def test_existing_attestation_prevents_duplicate_append(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "archive/closing-line-start-attestations/baseball_mlb/2026-09-12.ndjson"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"event_id": "e1"}) + "\n")
            self.assertIn("e1", mod._existing(root))


if __name__ == "__main__":
    unittest.main()
