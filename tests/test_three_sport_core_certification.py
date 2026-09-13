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
            # Passing MLB alone must never certify all three sports.
            self.assertFalse(report["all_three_core_certified"])

    def test_cfb_forward_snapshot_never_substitutes_for_historical_pit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snap = root / "history/cfb/forward-pit/20260912T150619Z-test"
            snap.mkdir(parents=True)
            (snap / "readiness.json").write_text(json.dumps({"status": "AVAILABLE"}))
            report = audit(root)
            self.assertEqual(report["sports"]["CFB"]["latest_forward_pit_status"], "AVAILABLE")
            self.assertFalse(report["sports"]["CFB"]["historical_pit_training_bundle_present"])
            self.assertEqual(report["sports"]["CFB"]["status"], "BLOCKED_HISTORICAL_PIT_TRAINING_BUNDLE_MISSING")


if __name__ == "__main__":
    unittest.main()
