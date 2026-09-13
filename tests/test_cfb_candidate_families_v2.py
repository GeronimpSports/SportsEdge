import unittest

from sportsedge.sports.cfb.candidate_families import CFBCandidateFamilyError, IMPLEMENTED_FAMILIES, materialize_candidate_row

KEYS = (
    "off_ppa_rush", "off_ppa_dropback", "def_ppa_rush_allowed", "def_ppa_dropback_allowed",
    "off_success_rate", "def_success_rate_allowed", "standard_down_ppa",
    "passing_down_success_rate", "eckel_rate", "points_per_eckel", "points_per_drive",
    "net_field_position", "explosive_rate",
)


def metric(season, through_week, source, value):
    out = {key: float(value) for key in KEYS}
    out.update({"team": "T", "season": season, "through_week": through_week, "sample_source": source})
    return out


def row():
    current = metric(2026, 2, "CURRENT_SEASON_PRIOR_WEEKS", 4.0)
    prior = metric(2025, 99, "PRIOR_SEASON_FALLBACK", 2.0)
    return {
        "season": 2026, "week": 3, "neutral_site": False, "weather": {"game_indoor": True},
        "home_metrics": current, "away_metrics": current,
        "home_prior_metrics": prior, "away_prior_metrics": prior,
        "home_current_metrics": current, "away_current_metrics": current,
        "home_games_in_sample": 2, "away_games_in_sample": 3,
    }


class TestCandidateFamiliesV2(unittest.TestCase):
    def test_all_four_are_executable(self):
        self.assertEqual(len(IMPLEMENTED_FAMILIES), 4)

    def test_reliability_switch_threshold_is_three(self):
        out = materialize_candidate_row("RELIABILITY_WEIGHTED_HARD_SWITCH", row(), constants={"min_current_games": 3})
        self.assertEqual(out["home_metrics"]["sample_source"], "PRIOR_SEASON_FALLBACK")
        self.assertEqual(out["away_metrics"]["sample_source"], "CURRENT_SEASON_PRIOR_WEEKS")

    def test_blend_ramp_is_four_games(self):
        out = materialize_candidate_row("PRIOR_CURRENT_BLEND", row(), constants={"full_current_games": 4})
        self.assertEqual(out["home_metrics"]["off_ppa_rush"], 3.0)
        self.assertEqual(out["away_metrics"]["off_ppa_rush"], 3.5)

    def test_games_feature_is_explicit(self):
        out = materialize_candidate_row("GAMES_IN_SAMPLE_FEATURE", row(), constants={})
        self.assertEqual(out["candidate_extra_features"], {"home_games_in_sample": 2.0, "away_games_in_sample": 3.0})

    def test_constants_cannot_drift(self):
        with self.assertRaises(CFBCandidateFamilyError):
            materialize_candidate_row("RELIABILITY_WEIGHTED_HARD_SWITCH", row(), constants={"min_current_games": 4})

    def test_market_data_is_rejected(self):
        bad = row(); bad["spread"] = -3.5
        with self.assertRaises(CFBCandidateFamilyError):
            materialize_candidate_row("PRIOR_CURRENT_BLEND", bad, constants={"full_current_games": 4})


if __name__ == "__main__":
    unittest.main()
