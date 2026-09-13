from pathlib import Path
import json
import unittest

# Bootstrap-only touch: the workflow was introduced on the prior main commit.
ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "config/research/nfl_v2i_shared_game_regime_prereg_2026-09-12.json"
WORKFLOW = ROOT / ".github/workflows/nfl-v2i-first-readout.yml"


class NFLV2IFirstReadoutGovernanceTests(unittest.TestCase):
    def test_prereg_freezes_active_gates_before_readout(self):
        payload = json.loads(PREREG.read_text(encoding="utf-8"))
        gates = payload["frozen_evaluation_gates"]
        authority = payload["authority"]
        constraints = payload["implementation_constraints"]
        self.assertEqual(gates["signed_key_number_tolerance"], 0.005)
        self.assertEqual(gates["fold_win_rate_min"], 0.65)
        self.assertFalse(authority["promotion_authority"])
        self.assertFalse(authority["model_p_authority"])
        self.assertFalse(authority["official_status_granted"])
        self.assertFalse(constraints["post_first_readout_retuning_allowed"])
        self.assertEqual(payload["nfl_props"], "NO_ENGINE")

    def test_first_readout_workflow_cannot_promote_or_retune(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--max-abs-error 0.005", text)
        self.assertIn("NFL_V2I_PROMOTION_AUTHORITY_FORBIDDEN", text)
        self.assertIn("NFL_V2I_MODEL_P_AUTHORITY_FORBIDDEN", text)
        self.assertIn("NFL_V2I_POST_READOUT_RETUNING_FORBIDDEN", text)
        self.assertIn("NFL_PROPS_MUST_REMAIN_NO_ENGINE", text)
        self.assertIn("run_nfl_v2i_first_readout.py", text)
        self.assertIn("validate_nfl_v2i_candidate.py", text)


if __name__ == "__main__":
    unittest.main()
