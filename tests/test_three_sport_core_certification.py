import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_three_sport_core_certification import audit


class ThreeSportCoreCertificationTests(unittest.TestCase):
    def test_fail_closed_with_missing_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            report = audit(Path(td))
        self.assertFalse(report["all_three_core_certified"])
        self.assertEqual(report["sports"]["NFL"]["status"], "BLOCKED_NO_FORWARD_ARCHIVE")
        self.assertEqual(report["sports"]["CFB"]["status"], "BLOCKED_HISTORICAL_PIT_TRAINING_BUNDLE_MISSING")
        self.assertEqual(report["sports"]["MLB"]["status"], "BLOCKED_CORE_GATES_INCOMPLETE")
        self.assertFalse(report["authority"]["model_p_created"])
        self.assertFalse(report["authority"]["official_bet_created"])

    def test_mlb_requires_all_six_gates_for_all_core_markets(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "runtime/model-validation/SUMMARY/latest"
            p.mkdir(parents=True)
            gates = {
                name: {
                    gate: {"status": "PASS"}
                    for gate in (
                        "historical_point_in_time",
                        "untouched_holdout",
                        "calibration",
                        "settlement_semantics",
                        "production_parity",
                        "forward_evidence",
                    )
                }
                for name in ("MONEYLINE", "RUN_LINE", "TOTALS")
            }
            (p / "derived_status.json").write_text(json.dumps({"markets": gates}))
            report = audit(root)
            self.assertEqual(report["sports"]["MLB"]["status"], "CORE_GATES_PASS")
            self.assertFalse(report["all_three_core_certified"])

    def test_cfb_forward_snapshot_never_substitutes_for_historical_pit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snap = root / "history/cfb/forward-pit/20260912T150619Z-test"
            snap.mkdir(parents=True)
            (snap / "readiness.json").write_text(json.dumps({"status": "AVAILABLE"}))
            report = audit(root)
            self.assertEqual(report["sports"]["CFB"]["latest_forward_pit_status"], "AVAILABLE")
            self.assertEqual(report["sports"]["CFB"]["latest_forward_pit_status_source"], "readiness.json")
            self.assertFalse(report["sports"]["CFB"]["historical_pit_training_bundle_present"])
            self.assertEqual(report["sports"]["CFB"]["status"], "BLOCKED_HISTORICAL_PIT_TRAINING_BUNDLE_MISSING")

    def test_current_cfb_capture_classification_is_reported_without_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snap = root / "history/cfb/forward-pit/20260912T150619Z-test/capture"
            snap.mkdir(parents=True)
            (snap / "classification.json").write_text(json.dumps({
                "pit_classification": "FORWARD_SOURCE_SNAPSHOT_FROM_RETRIEVAL_TIME_ONLY",
                "promotion_evidence": False,
                "retroactive_point_in_time_claim": False,
            }))
            report = audit(root)
            cfb = report["sports"]["CFB"]
            self.assertEqual(cfb["latest_forward_pit_status"], "FORWARD_SOURCE_SNAPSHOT_FROM_RETRIEVAL_TIME_ONLY")
            self.assertEqual(cfb["latest_forward_pit_status_source"], "capture/classification.json")
            self.assertEqual(cfb["status"], "BLOCKED_HISTORICAL_PIT_TRAINING_BUNDLE_MISSING")

    def test_nfl_v2h_failed_readout_is_frozen_non_authoritative(self):
        row = json.loads(Path("sportsedge/sports/nfl/NFL_V2H_FIRST_READOUT_RESULT_2026-09-12.json").read_text())
        self.assertEqual(row["readout_status"], "REJECTED_FROZEN_ATTEMPT")
        self.assertFalse(row["frozen_readout"]["spread"]["historical_predictive_pass"])
        self.assertFalse(row["frozen_readout"]["total"]["historical_predictive_pass"])
        self.assertFalse(row["frozen_readout"]["emergent_key_fit"]["pass"])
        governance = row["governance"]
        self.assertTrue(governance["preregistration_locked"])
        self.assertFalse(governance["post_readout_retuning_allowed"])
        self.assertFalse(governance["may_reuse_same_readout_as_untouched_for_revised_candidate"])
        for key in ("model_p_authority", "promotion_authority", "promotion_eligible", "eligibility_changed", "edge_floor_changed", "official_status_granted"):
            self.assertFalse(governance[key], key)


if __name__ == "__main__":
    unittest.main()
