from pathlib import Path
import unittest
from unittest.mock import patch

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT
from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2j_candidate import (
    _feature_vector as feature_vector_reference,
    fit_nfl_m2_v2j_candidate,
)
from sportsedge.sports.nfl.m2_v2j_runtime_cache import market_readout_exact_cached
from sportsedge.sports.nfl.m2_v2j_validation import _market_readout
from sportsedge.sports.nfl.m2_v2i_candidate import (
    _offense_drive_probabilities as offense_drive_reference,
    _repeat_convolution as repeat_reference,
)


ROOT = Path(__file__).resolve().parents[1]


def feature(team_shift=0.0, qb="QB1"):
    return {
        "feature_contract": NFL_M2_FEATURE_CONTRACT,
        "qb_id": qb,
        "feature_asof_ts": "2026-09-01T12:00:00+00:00",
        "adj_off_epa": 0.10 + team_shift,
        "adj_def_epa": -0.02 - team_shift,
        "pass_epa": 0.12 + team_shift,
        "rush_epa": 0.01 + team_shift,
        "pressure_for": 0.30 + team_shift * 0.1,
        "pressure_allowed": 0.25 - team_shift * 0.1,
        "success_rate": 0.44 + team_shift * 0.1,
        "explosive_rate": 0.11 + team_shift * 0.05,
        "rest_diff_days": 1.0,
        "travel_miles": 300.0,
        "timezone_crossings": 0.0,
        "short_week": 0.0,
        "bye_week": 0.0,
        "wind_mph": 5.0,
        "roof_closed": 0.0,
        "qb_adjustment": team_shift,
        "prior_efficiency": 0.02 + team_shift,
        "prior_weight": 0.4,
    }


def event(home, away, season, hd, ad, htd, atd, hfg, afg):
    return {
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "home_team": home,
        "away_team": away,
        "season": season,
        "home_drives": hd,
        "away_drives": ad,
        "home_td_xp_good": htd,
        "away_td_xp_good": atd,
        "home_td_xp_miss": 0,
        "away_td_xp_miss": 0,
        "home_td_two_good": 0,
        "away_td_two_good": 0,
        "home_td_two_fail": 0,
        "away_td_two_fail": 0,
        "home_field_goals": hfg,
        "away_field_goals": afg,
        "home_other_no_score": hd - htd - hfg,
        "away_other_no_score": ad - atd - afg,
        "home_safeties": 0,
        "away_safeties": 0,
    }


def training_features():
    return [
        {"home_features": feature(0.2, "QA"), "away_features": feature(-0.2, "QB"), "home_score": 27, "away_score": 17},
        {"home_features": feature(-0.1, "QB"), "away_features": feature(0.1, "QA"), "home_score": 20, "away_score": 23},
        {"home_features": feature(0.3, "QA"), "away_features": feature(-0.3, "QB"), "home_score": 30, "away_score": 16},
        {"home_features": feature(-0.2, "QB"), "away_features": feature(0.2, "QA"), "home_score": 17, "away_score": 24},
        {"home_features": feature(0.05, "QA"), "away_features": feature(-0.05, "QB"), "home_score": 24, "away_score": 21},
        {"home_features": feature(-0.15, "QB"), "away_features": feature(0.15, "QA"), "home_score": 19, "away_score": 26},
    ]


def training_events():
    return [
        event("A", "B", 2022, 10, 11, 3, 2, 2, 1),
        event("B", "A", 2022, 12, 10, 2, 2, 2, 1),
        event("A", "B", 2023, 11, 12, 3, 1, 1, 2),
        event("B", "A", 2023, 10, 10, 2, 2, 1, 1),
        event("A", "B", 2024, 12, 11, 2, 2, 2, 1),
        event("B", "A", 2024, 11, 12, 2, 3, 1, 1),
    ]


def prediction_row(spread=-2.5, total=44.5):
    return {
        "home_team": "A",
        "away_team": "B",
        "home_features": feature(0.25, "QA"),
        "away_features": feature(-0.10, "QB"),
        "spread_line": spread,
        "total_line": total,
    }


class NFLV2JRuntimeCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = fit_nfl_m2_v2j_candidate(training_events(), training_features())

    def test_cached_readout_is_bit_exact_for_half_integer_and_missing_lines(self):
        rows = [
            prediction_row(-2.5, 44.5),
            prediction_row(-3.0, 45.0),
            prediction_row(None, 41.5),
            prediction_row(7.0, None),
            prediction_row(None, None),
        ]
        for row in rows:
            with self.subTest(spread=row["spread_line"], total=row["total_line"]):
                self.assertEqual(market_readout_exact_cached(self.model, row), _market_readout(self.model, row))

    def test_cached_readout_reduces_repeat_convolution_calls_without_changing_output(self):
        row = prediction_row(-3.0, 45.0)
        with patch(
            "sportsedge.sports.nfl.m2_v2j_validation._repeat_convolution",
            wraps=repeat_reference,
        ) as reference_calls:
            expected = _market_readout(self.model, row)
        with patch(
            "sportsedge.sports.nfl.m2_v2j_runtime_cache._repeat_convolution",
            wraps=repeat_reference,
        ) as cached_calls:
            actual = market_readout_exact_cached(self.model, row)
        self.assertEqual(actual, expected)
        self.assertLess(cached_calls.call_count, reference_calls.call_count)

    def test_conditioning_invariants_are_computed_once_per_direction(self):
        row = prediction_row(-3.0, 45.0)
        with patch(
            "sportsedge.sports.nfl.m2_v2j_runtime_cache._feature_vector",
            wraps=feature_vector_reference,
        ) as feature_calls, patch(
            "sportsedge.sports.nfl.m2_v2j_runtime_cache._offense_drive_probabilities",
            wraps=offense_drive_reference,
        ) as drive_calls:
            actual = market_readout_exact_cached(self.model, row)
        self.assertEqual(actual, _market_readout(self.model, row))
        self.assertEqual(feature_calls.call_count, 4)
        self.assertEqual(drive_calls.call_count, 2)
        self.assertGreater(len(self.model.shared_environment), 1)

    def test_contingency_is_not_wired_into_frozen_first_readout_workflow(self):
        workflow = (ROOT / ".github/workflows/nfl-v2j-first-readout.yml").read_text(encoding="utf-8")
        script = (ROOT / "scripts/run_nfl_v2j_first_readout.py").read_text(encoding="utf-8")
        self.assertNotIn("m2_v2j_runtime_cache", workflow)
        self.assertNotIn("m2_v2j_runtime_cache", script)


if __name__ == "__main__":
    unittest.main()
