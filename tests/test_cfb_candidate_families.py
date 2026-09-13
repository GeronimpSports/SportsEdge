import unittest
from sportsedge.sports.cfb.candidate_families import CFBCandidateFamilyError, FAMILY_EQUAL_WEIGHT_HARD_SWITCH, TEAM_METRIC_KEYS, materialize_candidate_row as baseline_materialize
from sportsedge.sports.cfb.candidate_registry_v2 import IMPLEMENTED_FAMILIES, EQUAL, RELIABILITY, BLEND, GAMES, materialize_candidate_row

def metrics(season,through_week,source,games=0,value=.1):
    x={k:value for k in TEAM_METRIC_KEYS};x.update(season=season,through_week=through_week,sample_source=source,games_in_sample=games);return x
class TestCFBCandidateFamilies(unittest.TestCase):
    def base(self,week=4,games=3):
        return {"season":2025,"week":week,"home_prior_metrics":metrics(2024,99,"PRIOR_SEASON_FALLBACK",12,.05),"away_prior_metrics":metrics(2024,99,"PRIOR_SEASON_FALLBACK",12,.05),"home_current_metrics":metrics(2025,week-1,"CURRENT_SEASON_PRIOR_WEEKS",games,.2),"away_current_metrics":metrics(2025,week-1,"CURRENT_SEASON_PRIOR_WEEKS",games,.2)}
    def test_all_four_predeclared_families_are_executable(self): self.assertEqual(IMPLEMENTED_FAMILIES,{EQUAL,RELIABILITY,BLEND,GAMES})
    def test_reliability_switch_threshold_is_frozen_at_three(self):
        r=self.base(games=2);self.assertEqual(materialize_candidate_row(RELIABILITY,r)["home_metrics"]["off_ppa_rush"],.05)
        r=self.base(games=3);self.assertEqual(materialize_candidate_row(RELIABILITY,r)["home_metrics"]["off_ppa_rush"],.2)
    def test_prior_current_blend_uses_frozen_four_game_prior_strength(self):
        out=materialize_candidate_row(BLEND,self.base(games=4));self.assertAlmostEqual(out["home_current_weight"],.5);self.assertAlmostEqual(out["home_metrics"]["off_ppa_rush"],.125)
    def test_games_feature_is_bounded_and_market_blind(self):
        out=materialize_candidate_row(GAMES,self.base(games=20));self.assertEqual(out["home_games_in_sample_feature"],1.0)
        r=self.base();r["spread"]=-3.5
        with self.assertRaisesRegex(CFBCandidateFamilyError,"MARKET_DATA_PROHIBITED"):materialize_candidate_row(GAMES,r)
    def test_runtime_constant_override_is_blocked(self):
        with self.assertRaisesRegex(CFBCandidateFamilyError,"RUNTIME_CONSTANT_OVERRIDE_PROHIBITED"):materialize_candidate_row(BLEND,self.base(),{"prior":99})
    def test_legacy_baseline_still_fails_closed_on_bad_week_identity(self):
        r={"season":2025,"week":4,"home_metrics":metrics(2025,2,"CURRENT_SEASON_PRIOR_WEEKS"),"away_metrics":metrics(2025,3,"CURRENT_SEASON_PRIOR_WEEKS")}
        with self.assertRaisesRegex(CFBCandidateFamilyError,"CURRENT_SEASON_SWITCH_INVALID"):baseline_materialize(FAMILY_EQUAL_WEIGHT_HARD_SWITCH,r)
if __name__=="__main__":unittest.main()
