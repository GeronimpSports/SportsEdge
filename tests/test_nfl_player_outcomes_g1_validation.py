import unittest

from sportsedge.sports.nfl.player_outcomes_g1_validation import (
    chronological_receptions_readout,
    probability_metrics,
    quantity_metrics,
)


class NFLPlayerOutcomeG1ValidationTests(unittest.TestCase):
    def test_probability_metrics(self):
        result = probability_metrics([(1, 0.8), (0, 0.2)])
        self.assertEqual(result["n"], 2)
        self.assertLess(result["brier"], 0.05)
        self.assertLess(result["log_loss"], 0.3)

    def test_quantity_metrics(self):
        result = quantity_metrics([(5, 4), (3, 4)])
        self.assertEqual(result["n"], 2)
        self.assertAlmostEqual(result["mae"], 1.0)
        self.assertAlmostEqual(result["rmse"], 1.0)

    def test_walk_forward_never_uses_current_outcome(self):
        rows = []
        for week, receptions in enumerate([2, 3, 4, 5, 6, 20], start=1):
            rows.append({
                "player_id": "p1",
                "season": 2025,
                "week": week,
                "receptions": receptions,
            })
        out = chronological_receptions_readout(rows, line=4.5, min_prior_games=5)
        self.assertEqual(out["probability_metrics"]["n"], 1)
        pred = out["predictions"][0]
        self.assertEqual(pred["week"], 6)
        self.assertAlmostEqual(pred["predicted_mean"], 4.0)
        self.assertEqual(pred["actual_receptions"], 20.0)
        self.assertFalse(out["random_split_used"])
        self.assertFalse(out["market_prices_consumed"])


if __name__ == "__main__":
    unittest.main()
