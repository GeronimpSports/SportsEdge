import unittest

from sportsedge.sports.nfl.prop_volume_stage1 import NFLVolumeStage1
from sportsedge.sports.nfl.prop_efficiency_engine import build_efficiency_distribution as nfl_eff
from sportsedge.sports.nfl.prop_joint_stage3 import build_joint_player_distribution as nfl_joint
from sportsedge.sports.cfb.prop_joint_stage3 import build_joint_player_distribution as cfb_joint
from sportsedge.sports.mlb.prop_volume_stage1 import MLBVolumeStage1
from sportsedge.sports.mlb.prop_efficiency_engine import build_efficiency_distribution as mlb_eff
from sportsedge.sports.mlb.prop_joint_stage3 import build_hitter_distribution, build_pitcher_distribution


class FootballJointStage3Tests(unittest.TestCase):
    def _pass_inputs(self):
        vol = NFLVolumeStage1().project(
            player_id="qb1", metric="pass_attempts",
            history=[{"pass_attempts": 31}, {"pass_attempts": 35}, {"pass_attempts": 33}],
            team_opportunity_mean=34, role_share=1.0,
        )
        eff = {
            "completion_rate": nfl_eff("completion_rate", {"baseline": 0.66, "uncertainty": 0.05}),
            "yards_per_attempt": nfl_eff("yards_per_attempt", {"baseline": 7.4, "uncertainty": 1.1}),
        }
        return vol, eff

    def test_nfl_joint_is_deterministic_and_coherent(self):
        vol, eff = self._pass_inputs()
        a = nfl_joint(player_id="qb1", volume={"pass_attempts": vol}, efficiency=eff, seed=17, paths=2000)
        b = nfl_joint(player_id="qb1", volume={"pass_attempts": vol}, efficiency=eff, seed=17, paths=2000)
        self.assertEqual(a.samples, b.samples)
        self.assertEqual(a.status, "RESEARCH_ONLY_NO_MARKET_BINDING")
        self.assertTrue(all(r["completions"] <= r["pass_attempts"] for r in a.samples))
        self.assertTrue(0 <= a.probability_over("passing_yards", 249.5) <= 1)

    def test_cfb_has_distinct_identity(self):
        vol, eff = self._pass_inputs()
        out = cfb_joint(player_id="qb1", volume={"pass_attempts": vol}, efficiency=eff, seed=4, paths=1000)
        self.assertEqual(out.model_id, "CFB_PROP_JOINT_STAGE3_V1")

    def test_market_context_rejected(self):
        vol, eff = self._pass_inputs()
        with self.assertRaises(ValueError):
            nfl_joint(player_id="qb1", volume={"pass_attempts": vol}, efficiency=eff, seed=1, paths=1000, pit_context={"sportsbook": "DK"})


class MLBJointStage3Tests(unittest.TestCase):
    def _hitter(self):
        pa = MLBVolumeStage1().project(player_id="h1", metric="plate_appearances", history=[{"plate_appearances": 4}, {"plate_appearances": 5}], role_opportunity_mean=4.5)
        eff = {
            "strikeout_rate": mlb_eff("strikeout_rate", {"baseline": .22}),
            "walk_rate": mlb_eff("walk_rate", {"baseline": .09}),
            "hit_rate": mlb_eff("hit_rate", {"baseline": .28}),
            "extra_base_hit_rate": mlb_eff("extra_base_hit_rate", {"baseline": .35}),
        }
        return pa, eff

    def test_hitter_joint_deterministic_and_coherent(self):
        pa, eff = self._hitter()
        a = build_hitter_distribution(player_id="h1", plate_appearances=pa, efficiency=eff, seed=9, paths=2000)
        b = build_hitter_distribution(player_id="h1", plate_appearances=pa, efficiency=eff, seed=9, paths=2000)
        self.assertEqual(a.samples, b.samples)
        self.assertTrue(all(r["extra_base_hits"] <= r["hits"] for r in a.samples))
        self.assertTrue(all(r["total_bases"] >= r["hits"] for r in a.samples))

    def test_pitcher_outcomes_do_not_exceed_bf(self):
        bf = MLBVolumeStage1().project(player_id="p1", metric="batters_faced", history=[{"batters_faced": 22}, {"batters_faced": 25}], role_opportunity_mean=24)
        eff = {
            "strikeout_rate": mlb_eff("strikeout_rate", {"baseline": .26}),
            "walk_rate": mlb_eff("walk_rate", {"baseline": .08}),
            "hit_rate": mlb_eff("hit_rate", {"baseline": .24}),
        }
        out = build_pitcher_distribution(player_id="p1", batters_faced=bf, efficiency=eff, seed=11, paths=1500)
        self.assertTrue(all(r["outs"] + r["walks_allowed"] + r["hits_allowed"] == r["batters_faced"] for r in out.samples))
        self.assertEqual(out.status, "RESEARCH_ONLY_NO_MARKET_BINDING")


if __name__ == "__main__":
    unittest.main()
