import unittest

from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2i_candidate import (
    NFL_M2_V2I_CANDIDATE_MODEL_ID,
    NFL_M2_V2I_DISTRIBUTION_CONTRACT,
    derive_nfl_m2_v2i_score_distribution,
    fit_nfl_m2_v2i_candidate,
)


def event_row(game_id, season, home_drives, away_drives, *, market_shift=0.0):
    def side(prefix, drives, td7, fg, td6=0, td8=0, safety=0):
        used = td7 + fg + td6 + td8
        return {
            f"{prefix}_drives": drives,
            f"{prefix}_td_xp_good": td7,
            f"{prefix}_td_xp_miss": td6,
            f"{prefix}_td_two_good": td8,
            f"{prefix}_td_two_fail": 0,
            f"{prefix}_field_goals": fg,
            f"{prefix}_safeties": safety,
            f"{prefix}_other_no_score": drives - used,
        }

    row = {
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "game_id": game_id,
        "season": season,
        "home_team": "AAA",
        "away_team": "BBB",
        "spread_line": -3.0 + market_shift,
        "total_line": 44.5 + market_shift,
        "home_moneyline": -150.0 + market_shift,
        "away_moneyline": 130.0 + market_shift,
    }
    row.update(side("home", home_drives, td7=2, fg=1, safety=1 if game_id.endswith("2") else 0))
    row.update(side("away", away_drives, td7=1, fg=2, td8=1 if game_id.endswith("3") else 0))
    return row


class NFLM2V2ICandidateTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            event_row("g1", 2020, 10, 12),
            event_row("g2", 2020, 10, 12),
            event_row("g3", 2021, 13, 9),
            event_row("g4", 2021, 13, 9),
        ]

    def test_fit_preserves_joint_possession_regime_not_cross_product(self):
        model = fit_nfl_m2_v2i_candidate(self.rows)
        self.assertEqual(model.model_id, NFL_M2_V2I_CANDIDATE_MODEL_ID)
        self.assertEqual(model.distribution_contract, NFL_M2_V2I_DISTRIBUTION_CONTRACT)
        support = {(home, away) for home, away, _weight in model.possession_regime}
        self.assertEqual(support, {(10, 12), (13, 9)})
        self.assertNotIn((10, 9), support)
        self.assertNotIn((13, 12), support)
        self.assertAlmostEqual(sum(weight for _home, _away, weight in model.possession_regime), 1.0, places=12)

    def test_distribution_is_integer_joint_support_and_normalized(self):
        model = fit_nfl_m2_v2i_candidate(self.rows)
        distribution = derive_nfl_m2_v2i_score_distribution(
            model, {"home_team": "AAA", "away_team": "BBB"}
        )
        self.assertTrue(distribution)
        self.assertAlmostEqual(sum(float(row["weight"]) for row in distribution), 1.0, places=10)
        for row in distribution:
            self.assertIsInstance(row["home_score"], int)
            self.assertIsInstance(row["away_score"], int)
            self.assertEqual(row["margin"], row["home_score"] - row["away_score"])
            self.assertEqual(row["total"], row["home_score"] + row["away_score"])
            self.assertGreaterEqual(float(row["weight"]), 0.0)

    def test_market_fields_cannot_change_fit_or_distribution(self):
        shifted = [dict(row) for row in self.rows]
        for index, row in enumerate(shifted):
            row["spread_line"] = 40.0 + index
            row["total_line"] = 100.0 + index
            row["home_moneyline"] = -900.0 + index
            row["away_moneyline"] = 700.0 + index
        model_a = fit_nfl_m2_v2i_candidate(self.rows)
        model_b = fit_nfl_m2_v2i_candidate(shifted)
        self.assertEqual(model_a, model_b)
        game_a = {"home_team": "AAA", "away_team": "BBB", "spread_line": -3.0, "total_line": 44.5}
        game_b = {"home_team": "AAA", "away_team": "BBB", "spread_line": 17.5, "total_line": 71.0}
        self.assertEqual(
            derive_nfl_m2_v2i_score_distribution(model_a, game_a),
            derive_nfl_m2_v2i_score_distribution(model_a, game_b),
        )

    def test_invalid_drive_partition_fails_closed(self):
        broken = [dict(row) for row in self.rows]
        broken[0]["home_other_no_score"] += 1
        with self.assertRaisesRegex(ValueError, "NFL_M2_V2I_DRIVE_PARTITION_INVALID"):
            fit_nfl_m2_v2i_candidate(broken)


if __name__ == "__main__":
    unittest.main()
