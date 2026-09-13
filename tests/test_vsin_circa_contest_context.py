import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.capture_vsin_circa_contest_context import build_manifest, parse_summary


RAW = b"""
<html><body>
<h1>Circa Football Invitational 2026</h1>
<div>Week 1 Splits</div>
<div>All 51 NFL 13 CFB 38</div>
<div>Updated 2026-09-12 10:28:06</div>
</body></html>
"""


class VsinContestContextTests(unittest.TestCase):
    def test_policy_registers_sources_without_decision_authority(self):
        policy = json.loads(Path("config/football_external_context_v1.json").read_text())
        self.assertEqual(policy["policy_id"], "FOOTBALL_EXTERNAL_CONTEXT_V1")
        authority = policy["authority"]
        for key, value in authority.items():
            self.assertFalse(value, key)
        self.assertEqual(policy["sources"]["REDZONE_LABS"]["source_type"], "EXTERNAL_QUANTITATIVE_BENCHMARK")
        contest = policy["sources"]["VSIN_CIRCA_FRIDAY_FOOTBALL_INVITATIONAL_2026"]
        self.assertEqual(contest["source_type"], "HANDICAPPER_CONTEST_PICK_FREQUENCY")
        self.assertIn("not sportsbook ticket", contest["semantics"].lower())
        paper = policy["sources"]["ARXIV_2410_21484"]
        self.assertFalse(paper["runtime_authority"])
        self.assertTrue(policy["disagreement_log"]["enabled"])

    def test_summary_semantics(self):
        summary = parse_summary(RAW)
        self.assertEqual(summary["contest_week"], 1)
        self.assertEqual(summary["listed_games_all"], 51)
        self.assertEqual(summary["listed_games_nfl"], 13)
        self.assertEqual(summary["listed_games_cfb"], 38)
        self.assertEqual(summary["updated_at_source"], "2026-09-12 10:28:06")

    def test_manifest_is_diagnostic_only(self):
        now = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)
        row = build_manifest(RAW, "https://example.test/splits/", now)
        self.assertEqual(row["raw_sha256"], hashlib.sha256(RAW).hexdigest())
        self.assertTrue(row["context_only"])
        self.assertFalse(row["model_p_authority"])
        self.assertFalse(row["predictive_model_input"])
        self.assertFalse(row["truth_gate_input"])
        self.assertFalse(row["promotion_authority"])
        self.assertFalse(row["eligibility_authority"])
        self.assertFalse(row["edge_floor_authority"])
        self.assertFalse(row["staking_authority"])
        self.assertFalse(row["official_authority"])
        self.assertFalse(row["confidence_vote"])
        self.assertIn("not sportsbook tickets", row["semantics"])

    def test_identity_mismatch_fails_closed(self):
        with self.assertRaises(RuntimeError):
            parse_summary(b"<html><body>Some other page</body></html>")


if __name__ == "__main__":
    unittest.main()
