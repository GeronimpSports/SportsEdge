from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "config/research/nfl_v2i_shared_game_regime_prereg_2026-09-12.json"


class NFLV2IPreregGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(PREREG.read_text(encoding="utf-8"))

    def test_shared_game_regime_is_required_and_independent_marginals_forbidden(self):
        architecture = self.payload["architecture"]
        regime = architecture["game_regime"]
        self.assertEqual(architecture["class"], "SHARED_GAME_REGIME_POSSESSION_GENERATOR")
        self.assertIn("Home and away possession opportunity may not be generated as independent", regime["independence_forbidden"])
        self.assertTrue(architecture["drive_outcome_model"]["mutual_exclusivity"])
        self.assertTrue(architecture["market_blind"])
        self.assertFalse(architecture["sportsbook_price_features_allowed"])
        self.assertFalse(architecture["closing_line_features_allowed"])

    def test_v2h_readout_cannot_become_numeric_tuning_target(self):
        forbidden = self.payload["forbidden_inputs"]
        fit = self.payload["fit_and_selection"]
        self.assertIn("V2H signed-key residual values as a fitting or selection objective", forbidden)
        self.assertFalse(fit["v2h_readout_values_for_numeric_tuning"])
        self.assertEqual(fit["hyperparameter_selection"], "NESTED_TRAINING_ONLY")
        self.assertIn("no key-number objective", fit["selection_objective"])

    def test_frozen_gates_and_zero_authority_are_unchanged(self):
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
        self.assertTrue(constraints["production_registry_may_not_consume_v2i"])
        self.assertTrue(constraints["v2h_evidence_may_not_be_rewritten"])
        self.assertEqual(self.payload["nfl_props"], "NO_ENGINE")

    def test_first_readout_is_locked_before_any_v2i_result(self):
        constraints = self.payload["implementation_constraints"]
        self.assertTrue(constraints["first_historical_v2i_readout_before_model_family_change"])
        self.assertTrue(constraints["first_historical_v2i_readout_must_be_untuned"])
        self.assertFalse(constraints["post_first_readout_retuning_allowed"])
        self.assertEqual(self.payload["evaluation_plan"]["key_number_use"], "POST_FIT_DIAGNOSTIC_ONLY")


if __name__ == "__main__":
    unittest.main()
