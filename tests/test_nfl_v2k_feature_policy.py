import json
from pathlib import Path
import unittest


POLICY = Path("sportsedge/sports/nfl/NFL_V2K_FEATURE_POLICY_V1.json")


class NFLV2KFeaturePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text())

    def test_research_only_and_no_authority(self):
        p = self.policy
        self.assertEqual(p["schema"], "SPORTSEDGE_NFL_V2K_FEATURE_POLICY_V1")
        self.assertEqual(p["status"], "FROZEN_RESEARCH_ONLY")
        self.assertEqual(p["authority"], {"model_p": False, "promotion": False, "official": False})

    def test_identity_is_audit_only_not_model_input(self):
        p = self.policy
        self.assertTrue(p["identity_contract"]["identity_fields_are_not_model_features"])
        fit = set(p["fit_features"])
        identity = set(p["source_identity_fields"])
        self.assertTrue(fit.isdisjoint(identity))
        self.assertEqual(p["identity_contract"]["unique_drive_key"], ["game_id", "drive_id"])
        self.assertTrue(p["identity_contract"]["offense_must_differ_from_defense"])

    def test_field_position_semantics_are_frozen_and_no_guessing(self):
        c = self.policy["field_position_contract"]
        self.assertEqual(c["field"], "start_yard")
        self.assertEqual(c["semantic"], "yards_from_offense_own_goal_line")
        self.assertEqual(c["minimum"], 1.0)
        self.assertEqual(c["maximum"], 99.0)
        self.assertFalse(c["raw_provider_yardline_guessing_allowed"])
        self.assertEqual(set(c["bins"]), {"BACKED_UP", "OWN_TERRITORY", "PLUS_TERRITORY", "RED_ZONE"})

    def test_train_serve_parity_and_pit_denylist_are_explicit(self):
        p = self.policy
        self.assertEqual(p["train_serve_transform_contract"], "IDENTICAL")
        self.assertEqual(p["missing_required_feature_behavior"], "BLOCK")
        self.assertEqual(p["unknown_drive_result_behavior"], "BLOCK")
        prohibited = set(p["prohibited_feature_families"])
        self.assertIn("sportsbook_price_or_line", prohibited)
        self.assertIn("betting_split_or_handle", prohibited)
        self.assertIn("capper_or_consensus_opinion", prohibited)
        self.assertIn("postgame_or_future_information", prohibited)
        self.assertIn("2026_forward_outcome", prohibited)
        self.assertIn("feature_computed_using_rows_at_or_after_prediction_cutoff", prohibited)

    def test_drive_outcome_taxonomy_is_exact(self):
        self.assertEqual(
            set(self.policy["allowed_drive_outcomes"]),
            {"TD", "FG", "TURNOVER", "PUNT_OTHER", "SAFETY", "DEF_ST_TD"},
        )


if __name__ == "__main__":
    unittest.main()
