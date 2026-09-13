import unittest

from sportsedge.sports.nfl.m2_v2h_candidate import (
    NFL_M2_V2H_EVENT_CONTRACT,
    build_nfl_v2h_game_event_rows,
    derive_nfl_m2_v2h_score_distribution,
    fit_nfl_m2_v2h_candidate,
)


class NFLM2V2HCandidateTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for season in (2020, 2021):
            for week in (1, 2):
                rows.append({
                    "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
                    "game_id": f"{season}_{week}_B_A",
                    "season": season,
                    "week": week,
                    "home_team": "A",
                    "away_team": "B",
                    "home_drives": 10,
                    "home_td_xp_good": 2,
                    "home_td_xp_miss": 1 if week == 1 else 0,
                    "home_td_two_good": 0 if week == 1 else 1,
                    "home_td_two_fail": 0,
                    "home_field_goals": 1,
                    "home_safeties": 0,
                    "home_other_no_score": 6,
                    "away_drives": 10,
                    "away_td_xp_good": 2,
                    "away_td_xp_miss": 0,
                    "away_td_two_good": 0,
                    "away_td_two_fail": 1,
                    "away_field_goals": 1,
                    "away_safeties": 0,
                    "away_other_no_score": 6,
                })
        return rows

    def test_market_fields_cannot_change_distribution(self):
        model = fit_nfl_m2_v2h_candidate(self._rows())
        base = {"home_team": "A", "away_team": "B"}
        priced = dict(base, spread_line=17.5, total_line=61.5, home_spread_odds=250, away_spread_odds=-310)
        self.assertEqual(
            derive_nfl_m2_v2h_score_distribution(model, base),
            derive_nfl_m2_v2h_score_distribution(model, priced),
        )

    def test_distribution_is_normalized_integer_score_support(self):
        model = fit_nfl_m2_v2h_candidate(self._rows())
        distribution = derive_nfl_m2_v2h_score_distribution(model, {"home_team": "A", "away_team": "B"})
        self.assertAlmostEqual(sum(float(row["weight"]) for row in distribution), 1.0, places=10)
        self.assertTrue(all(isinstance(row["home_score"], int) and isinstance(row["away_score"], int) for row in distribution))

    def test_event_builder_keeps_explicit_conversion_states(self):
        schedule = [{"game_id": "2025_01_B_A", "season": 2025, "week": 1, "game_type": "REG", "home_team": "A", "away_team": "B"}]
        pbp = [
            {"game_id": "2025_01_B_A", "posteam": "A", "drive": "1", "touchdown": "1", "td_team": "A", "play_type": "pass", "extra_point_result": "", "two_point_conv_result": "", "field_goal_result": "", "safety": "0"},
            {"game_id": "2025_01_B_A", "posteam": "A", "drive": "1", "touchdown": "0", "td_team": "", "play_type": "extra_point", "extra_point_result": "good", "two_point_conv_result": "", "field_goal_result": "", "safety": "0"},
            {"game_id": "2025_01_B_A", "posteam": "A", "drive": "2", "touchdown": "0", "td_team": "", "play_type": "field_goal", "field_goal_result": "made", "extra_point_result": "", "two_point_conv_result": "", "safety": "0"},
            {"game_id": "2025_01_B_A", "posteam": "B", "drive": "1", "touchdown": "1", "td_team": "B", "play_type": "run", "extra_point_result": "", "two_point_conv_result": "", "field_goal_result": "", "safety": "0"},
            {"game_id": "2025_01_B_A", "posteam": "B", "drive": "1", "touchdown": "0", "td_team": "", "play_type": "two_point_attempt", "two_point_conv_result": "success", "extra_point_result": "", "field_goal_result": "", "safety": "0"},
            {"game_id": "2025_01_B_A", "posteam": "B", "drive": "2", "touchdown": "0", "td_team": "", "play_type": "run", "extra_point_result": "", "two_point_conv_result": "", "field_goal_result": "", "safety": "0"},
        ]
        rows = build_nfl_v2h_game_event_rows(schedule, pbp)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["home_td_xp_good"], 1)
        self.assertEqual(row["home_field_goals"], 1)
        self.assertEqual(row["away_td_two_good"], 1)
        self.assertEqual(row["away_other_no_score"], 1)


if __name__ == "__main__":
    unittest.main()
