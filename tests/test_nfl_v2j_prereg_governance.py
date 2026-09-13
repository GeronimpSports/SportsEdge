from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "config/research/nfl_v2j_conditioned_drive_regime_prereg_2026-09-12.json"


class NFLV2JPreregGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(PREREG.read_text(encoding="utf-8"))

    def test_conditioning_and_shared_environment_are_market_blind(self):
        architecture = self.payload["architecture"]
        conditioning = architecture["pregame_strength_conditioning"]
        environment = architecture["shared_game_environment"]
        self.assertEqual(architecture["class"], "PIT_CONDITIONED_DRIVE_MODEL_WITH_SHARED_SCORING_ENVIRONMENT")
        self.assertFalse(conditioning["sportsbook_or_closing_market_features"])
        self.assertTrue(environment["independent_home_away_environment_forbidden"])
        self.assertTrue(architecture["possession_and_scoring"]["joint_possession_regime_required"])
        self.assertTrue(architecture["market_blind"])

    def test_prior_failed_readouts_cannot_be_numeric_targets(self):
        forbidden = self.payload["forbidden_inputs"]
        fit = self.payload["fit_and_selection"]
        self.assertIn("V2H or V2I signed-key residual values as fitting or selection targets", forbidden)
        self.assertIn("V2I fold outcomes as hyperparameter targets", forbidden)
        self.assertFalse(fit["v2i_readout_values_for_numeric_tuning"])
        self.assertEqual(fit["hyperparameter_selection"], "NESTED_TRAINING_ONLY")
        self.assertIn("no key-number objective", fit["selection_objective"])

    def test_frozen_gates_and_zero_authority_remain(self):
        gates = self.payload["frozen_evaluation_gates"]
        authority = self.payload["authority"]
        constraints = self.payload["implementation_constraints"]
        self.assertEqual(gates["signed_key_number_tolerance"], 0.005)
        self.assertEqual(gates["fold_win_rate_min"], 0.65)
        self.assertTrue(gates["truth_gate_unchanged"])
        self.assertFalse(authority["promotion_authority"])
        self.assertFalse(authority["model_p_authority"])
        self.assertFalse(authority["official_status_granted"])
        self.assertFalse(authority["staking_authority"])
        self.assertTrue(constraints["production_m2_files_may_not_change"])
        self.assertTrue(constraints["production_registry_may_not_consume_v2j"])
        self.assertFalse(constraints["post_first_readout_retuning_allowed"])
        self.assertEqual(self.payload["nfl_props"], "NO_ENGINE")


if __name__ == "__main__":
    unittest.main()
