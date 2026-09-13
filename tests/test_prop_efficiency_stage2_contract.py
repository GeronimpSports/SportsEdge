import unittest

from sportsedge.sports.nfl.prop_efficiency_engine import build_efficiency_distribution as nfl_build
from sportsedge.sports.cfb.prop_efficiency_engine import build_efficiency_distribution as cfb_build
from sportsedge.sports.mlb.prop_efficiency_engine import build_efficiency_distribution as mlb_build


class Stage2EfficiencyContractTests(unittest.TestCase):
    def test_nfl_completion_rate_is_bounded_and_research_only(self):
        d = nfl_build("completion_rate", {"baseline": 0.67, "context_delta": 0.02, "uncertainty": 0.05})
        self.assertEqual(d.sport, "NFL")
        self.assertEqual(d.status, "RESEARCH_ONLY_NO_MARKET_BINDING")
        self.assertGreater(d.mean, 0.0)
        self.assertLess(d.mean, 1.0)

    def test_cfb_yards_per_attempt_is_supported(self):
        d = cfb_build("yards_per_attempt", {"baseline": 7.4, "context_delta": 0.3, "uncertainty": 1.1})
        self.assertAlmostEqual(d.mean, 7.7)
        self.assertGreater(d.probability_over(7.0), 0.5)

    def test_mlb_rate_metrics_are_bounded(self):
        d = mlb_build("strikeout_rate", {"baseline": 0.25, "context_delta": 0.03, "uncertainty": 0.04})
        self.assertAlmostEqual(d.mean, 0.28)
        self.assertGreater(d.probability_over(0.24), 0.5)

    def test_deterministic(self):
        args = {"baseline": 4.6, "context_delta": 0.2, "uncertainty": 0.8}
        a = nfl_build("yards_per_carry", args)
        b = nfl_build("yards_per_carry", args)
        self.assertEqual(a, b)
        self.assertEqual(a.probability_over(4.5), b.probability_over(4.5))

    def test_market_inputs_rejected_recursively_all_sports(self):
        dirty = {"baseline": 0.7, "context": {"sportsbook": {"line": 25.5}}}
        for builder, metric in ((nfl_build, "catch_rate"), (cfb_build, "catch_rate"), (mlb_build, "contact_rate")):
            with self.assertRaises(ValueError):
                builder(metric, dirty)

    def test_stage3_stats_not_smuggled_into_stage2(self):
        with self.assertRaises(ValueError):
            nfl_build("receiving_yards", {"baseline": 65.0})
        with self.assertRaises(ValueError):
            cfb_build("passing_yards", {"baseline": 250.0})
        with self.assertRaises(ValueError):
            mlb_build("hits", {"baseline": 1.2})


if __name__ == "__main__":
    unittest.main()
