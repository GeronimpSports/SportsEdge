import unittest

from sportsedge.sports.nfl.prop_volume_stage1 import NFLVolumeStage1, VolumeStage1Error
from sportsedge.sports.cfb.prop_volume_stage1 import CFBVolumeStage1
from sportsedge.sports.mlb.prop_volume_stage1 import MLBVolumeStage1, MLBVolumeStage1Error


class NFLVolumeStage1Tests(unittest.TestCase):
    def test_full_pmf_and_deterministic(self):
        engine = NFLVolumeStage1(decay=0.82, shrink_games=4)
        kwargs = dict(
            player_id="qb1",
            metric="pass_attempts",
            history=[{"pass_attempts": 31}, {"pass_attempts": 35}, {"pass_attempts": 37}],
            team_opportunity_mean=36.0,
            role_share=1.0,
            availability_probability=1.0,
        )
        a = engine.project(**kwargs)
        b = engine.project(**kwargs)
        self.assertEqual(a, b)
        self.assertAlmostEqual(sum(a.pmf), 1.0, places=12)
        self.assertEqual(a.status, "RESEARCH_ONLY_NO_MARKET_BINDING")
        self.assertGreater(a.probability_over(34.5), 0.0)
        self.assertLess(a.probability_over(34.5), 1.0)

    def test_market_fields_rejected(self):
        with self.assertRaises(VolumeStage1Error):
            NFLVolumeStage1().project(
                player_id="wr1",
                metric="targets",
                history=[{"targets": 7, "prop_line": 6.5}],
                team_opportunity_mean=35,
                role_share=0.22,
            )

    def test_unsupported_metric_rejected(self):
        with self.assertRaises(VolumeStage1Error):
            NFLVolumeStage1().project(
                player_id="wr1",
                metric="receiving_yards",
                history=[{"receiving_yards": 75}],
                team_opportunity_mean=35,
                role_share=0.22,
            )


class CFBVolumeStage1Tests(unittest.TestCase):
    def test_cfb_identity_and_mass(self):
        out = CFBVolumeStage1().project(
            player_id="rb1",
            metric="rush_attempts",
            history=[{"rush_attempts": 11}, {"rush_attempts": 16}, {"rush_attempts": 18}],
            team_opportunity_mean=42,
            role_share=0.40,
        )
        self.assertEqual(out.model_id, "CFB_PROP_VOLUME_STAGE1_V1")
        self.assertAlmostEqual(sum(out.pmf), 1.0, places=12)
        self.assertEqual(out.status, "RESEARCH_ONLY_NO_MARKET_BINDING")

    def test_cfb_rejects_book_input(self):
        with self.assertRaises(VolumeStage1Error):
            CFBVolumeStage1().project(
                player_id="wr1",
                metric="receptions",
                history=[{"receptions": 5, "sportsbook": "dk"}],
                team_opportunity_mean=36,
                role_share=0.18,
            )


class MLBVolumeStage1Tests(unittest.TestCase):
    def test_hitter_pa_distribution(self):
        out = MLBVolumeStage1().project(
            player_id="h1",
            metric="plate_appearances",
            history=[{"plate_appearances": 4}, {"plate_appearances": 5}, {"plate_appearances": 4}],
            role_opportunity_mean=4.5,
        )
        self.assertAlmostEqual(sum(out.pmf), 1.0, places=12)
        self.assertEqual(out.model_id, "MLB_PROP_VOLUME_STAGE1_V1")
        self.assertEqual(out.status, "RESEARCH_ONLY_NO_MARKET_BINDING")

    def test_pitcher_volume_distribution(self):
        out = MLBVolumeStage1().project(
            player_id="p1",
            metric="pitches_thrown",
            history=[{"pitches_thrown": 91}, {"pitches_thrown": 98}, {"pitches_thrown": 101}],
            role_opportunity_mean=96,
        )
        self.assertAlmostEqual(sum(out.pmf), 1.0, places=12)
        self.assertGreater(out.probability_over(95.5), 0.0)
        self.assertLess(out.probability_over(95.5), 1.0)

    def test_mlb_market_fields_rejected(self):
        with self.assertRaises(MLBVolumeStage1Error):
            MLBVolumeStage1().project(
                player_id="p1",
                metric="batters_faced",
                history=[{"batters_faced": 23, "over_price": -115}],
                role_opportunity_mean=24,
            )

    def test_efficiency_not_stage1(self):
        with self.assertRaises(MLBVolumeStage1Error):
            MLBVolumeStage1().project(
                player_id="h1",
                metric="hits",
                history=[{"hits": 2}],
                role_opportunity_mean=4.5,
            )


if __name__ == "__main__":
    unittest.main()
