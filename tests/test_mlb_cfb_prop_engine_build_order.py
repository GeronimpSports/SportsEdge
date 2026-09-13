import json
import unittest
from pathlib import Path

from sportsedge.market_ids import canonical_market_id

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "config/research/mlb_cfb_prop_engine_build_order_v1.json").read_text())


class GlobalRulesTests(unittest.TestCase):
    def test_market_binding_is_last(self):
        self.assertEqual(POLICY["global_rules"]["market_binding_stage"], 7)
        self.assertFalse(POLICY["global_rules"]["sportsbook_prices_may_influence_stages_1_through_6"])

    def test_research_inputs_cannot_create_model_p(self):
        rules = POLICY["global_rules"]
        self.assertFalse(rules["research_projections_may_create_model_p"])
        self.assertFalse(rules["hit_rates_may_create_model_p"])
        self.assertFalse(rules["provider_mappings_may_create_model_p"])

    def test_one_sided_rule_is_explicit(self):
        self.assertIn("UNAVAILABLE_ONE_SIDED", POLICY["global_rules"]["one_sided_price_rule"])


class MLBTests(unittest.TestCase):
    def test_mlb_distribution_before_market(self):
        mlb = POLICY["MLB"]
        self.assertIn("plate_appearances", mlb["stage_1_volume"])
        canonical_stage_3 = {
            canonical_market_id("mlb", market)
            for market in mlb["stage_3_joint_player_distributions"]
        }
        self.assertIn("pitcher_strikeouts", canonical_stage_3)
        self.assertTrue(mlb["stage_7_market_binding"]["bind_only_after_model_distribution_exists"])
        self.assertFalse(mlb["stage_6_validation"]["market_prices_as_model_features"])

    def test_mlb_home_run_engine_is_separate(self):
        engine = POLICY["MLB"]["stage_4_td_analogue_separate_event_engine"]
        self.assertEqual(engine["engine"], "HOME_RUN_EVENT_ENGINE")
        self.assertIn("kevin_roth_mysportsweather_context", POLICY["MLB"]["stage_5_pit_inputs"])


class CFBTests(unittest.TestCase):
    def test_cfb_volume_efficiency_distribution_order(self):
        cfb = POLICY["CFB"]
        self.assertIn("qb_pass_attempts", cfb["stage_1_volume"])
        self.assertIn("yards_per_attempt", cfb["stage_2_efficiency"])
        self.assertIn("receiving_yards", cfb["stage_3_joint_player_distributions"])
        self.assertTrue(cfb["stage_7_market_binding"]["bind_only_after_model_distribution_exists"])

    def test_cfb_td_engine_and_pit_constraints(self):
        cfb = POLICY["CFB"]
        self.assertIn("anytime_td_probability", cfb["stage_4_td_engine"]["outputs"])
        self.assertTrue(cfb["stage_5_source_constraints"]["all_inputs_timestamped_before_kickoff"])
        self.assertFalse(cfb["stage_5_source_constraints"]["capper_opinions_may_influence_model_or_recommendation"])


class AuthorityTests(unittest.TestCase):
    def test_blueprint_has_zero_betting_authority(self):
        authority = POLICY["authority"]
        self.assertFalse(authority["creates_model_p"])
        self.assertFalse(authority["promotes_market"])
        self.assertFalse(authority["grants_official"])
        self.assertFalse(authority["grants_staking"])
        self.assertEqual(POLICY["MLB"]["unsupported_market_status"], "NO_ENGINE")
        self.assertEqual(POLICY["CFB"]["unsupported_market_status"], "NO_ENGINE")


if __name__ == "__main__":
    unittest.main()
