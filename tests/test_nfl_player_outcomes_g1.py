import unittest

from sportsedge.sports.nfl.player_outcomes_g1 import (
    build_player_feature_rows,
    fit_count_distribution,
)


class NFLPlayerOutcomeG1Tests(unittest.TestCase):
    def test_features_use_only_prior_games(self):
        rows = []
        for week, receptions, targets, yards in [
            (1, 2, 4, 20),
            (2, 3, 5, 30),
            (3, 4, 6, 40),
            (4, 10, 12, 200),
        ]:
            rows.append({
                "player_id": "p1",
                "season": 2025,
                "week": week,
                "position": "WR",
                "team": "AAA",
                "opponent_team": "BBB",
                "receptions": receptions,
                "targets": targets,
                "receiving_yards": yards,
                "carries": 0,
                "rushing_yards": 0,
                "attempts": 0,
                "passing_yards": 0,
            })
        features = build_player_feature_rows(rows, min_prior_games=3)
        self.assertEqual(len(features), 1)
        row = features[0]
        self.assertEqual(row["week"], 4)
        self.assertAlmostEqual(row["receptions_l5"], 3.0)
        self.assertAlmostEqual(row["targets_l5"], 5.0)
        self.assertAlmostEqual(row["receiving_yards_l5"], 30.0)
        self.assertEqual(row["label_receptions"], 10)
        self.assertEqual(row["label_receiving_yards"], 200)

    def test_stable_player_id_required(self):
        rows = [
            {"player_id": "", "season": 2025, "week": 1},
            {"player_id": "", "season": 2025, "week": 2},
            {"player_id": "", "season": 2025, "week": 3},
            {"player_id": "", "season": 2025, "week": 4},
        ]
        with self.assertRaisesRegex(ValueError, "PLAYER_ID_REQUIRED"):
            build_player_feature_rows(rows, min_prior_games=3)

    def test_overdispersed_counts_choose_negative_binomial(self):
        dist = fit_count_distribution([0, 0, 1, 1, 2, 8, 10])
        self.assertEqual(dist.family, "negative_binomial")
        p = dist.prob_over_count_line(2.5)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, 1.0)

    def test_equally_dispersed_counts_use_poisson(self):
        dist = fit_count_distribution([2, 2, 2, 2, 2])
        self.assertEqual(dist.family, "poisson")


if __name__ == "__main__":
    unittest.main()
