import json
import tempfile
import unittest
from pathlib import Path

from sportsedge.mlb_acceptance_matrix import build_acceptance_matrix


HASH = "a" * 64


class MLBPITBindingContractTests(unittest.TestCase):
    def _status(self, pit_record):
        raw = json.loads(Path("config/mlb_validation_evidence.json").read_text())
        raw["markets"]["MONEYLINE"]["historical_point_in_time"] = pit_record
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "validation.json"
            path.write_text(json.dumps(raw))
            out = build_acceptance_matrix(validation_path=path)
        row = next(x for x in out["markets"] if x["market"] == "MONEYLINE")
        return row["current_state"]["validation_status"]["historical_point_in_time"], row

    def _valid(self):
        return {
            "status": "PASS",
            "pit_binding": {
                "observed_at_utc": "2026-07-01T22:00:00Z",
                "decision_at_utc": "2026-07-01T22:05:00Z",
                "source_snapshot_sha256": HASH,
                "retroactive_point_in_time_claim": False,
                "required_input_classes": ["lineup", "starting_pitcher"],
                "bound_inputs": {
                    "lineup": {
                        "identity": "game:123:lineup:home-away",
                        "observed_at_utc": "2026-07-01T22:00:00Z",
                        "source_snapshot_sha256": HASH,
                    },
                    "starting_pitcher": {
                        "identity": "game:123:starter:home-away",
                        "observed_at_utc": "2026-07-01T21:59:00Z",
                        "source_snapshot_sha256": HASH,
                    },
                },
            },
        }

    def test_bare_pass_cannot_satisfy_historical_pit(self):
        status, row = self._status({"status": "PASS"})
        self.assertEqual(status, "INVALID_PIT_BINDING")
        self.assertIn("historical_point_in_time", row["current_state"]["validation_missing"])
        self.assertFalse(row["acceptance_complete"])

    def test_retroactive_claim_is_rejected(self):
        record = self._valid()
        record["pit_binding"]["retroactive_point_in_time_claim"] = True
        status, _ = self._status(record)
        self.assertEqual(status, "INVALID_PIT_BINDING")

    def test_post_decision_observation_is_rejected(self):
        record = self._valid()
        record["pit_binding"]["observed_at_utc"] = "2026-07-01T22:06:00Z"
        status, _ = self._status(record)
        self.assertEqual(status, "INVALID_PIT_BINDING")

    def test_declared_lineup_or_starter_binding_cannot_be_missing(self):
        record = self._valid()
        del record["pit_binding"]["bound_inputs"]["starting_pitcher"]
        status, _ = self._status(record)
        self.assertEqual(status, "INVALID_PIT_BINDING")

    def test_valid_timestamp_and_lineup_starter_binding_passes_only_pit_gate(self):
        status, row = self._status(self._valid())
        self.assertEqual(status, "PASS")
        self.assertNotIn("historical_point_in_time", row["current_state"]["validation_missing"])
        self.assertTrue(row["current_state"]["validation_missing"])
        self.assertFalse(row["acceptance_complete"])


if __name__ == "__main__":
    unittest.main()
