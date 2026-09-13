from pathlib import Path
import unittest

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT
from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2j_parallel_validation import (
    build_nfl_m2_v2j_parallel_candidate_evidence,
    build_nfl_m2_v2j_parallel_raw_evaluations,
)
from sportsedge.sports.nfl.m2_v2j_validation import (
    build_nfl_m2_v2j_candidate_evidence,
    build_nfl_m2_v2j_raw_evaluations,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA = "1" * 64


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


def game_row(game_id, season, week, home, away, shift, home_score, away_score, spread, total):
    return {
        "game_id": game_id,
        "season": season,
        "week": week,
        "home_team": home,
        "away_team": away,
        "home_features": feature(shift, f"{home}Q"),
        "away_features": feature(-shift, f"{away}Q"),
        "home_score": home_score,
        "away_score": away_score,
        "spread_line": spread,
        "total_line": total,
        "home_spread_odds": -110,
        "away_spread_odds": -110,
        "over_odds": -105,
        "under_odds": -115,
    }


def event_row(game_id, season, home, away, hd, ad, htd, atd, hfg, afg):
    return {
        "game_id": game_id,
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


def fixtures():
    features = [
        game_row("2022_A_B", 2022, 1, "A", "B", 0.20, 27, 17, -2.5, 44.5),
        game_row("2022_B_A", 2022, 2, "B", "A", -0.10, 20, 23, 1.5, 43.5),
        game_row("2023_A_B", 2023, 1, "A", "B", 0.30, 30, 16, -3.0, 45.0),
        game_row("2023_B_A", 2023, 2, "B", "A", -0.20, 17, 24, 2.5, 42.5),
        game_row("2024_A_B", 2024, 1, "A", "B", 0.05, 24, 21, -2.5, 44.5),
        game_row("2024_B_A", 2024, 2, "B", "A", -0.15, 19, 26, 3.0, 45.0),
    ]
    events = [
        event_row("2022_A_B", 2022, "A", "B", 10, 11, 3, 2, 2, 1),
        event_row("2022_B_A", 2022, "B", "A", 12, 10, 2, 2, 2, 1),
        event_row("2023_A_B", 2023, "A", "B", 11, 12, 3, 1, 1, 2),
        event_row("2023_B_A", 2023, "B", "A", 10, 10, 2, 2, 1, 1),
        event_row("2024_A_B", 2024, "A", "B", 12, 11, 2, 2, 2, 1),
        event_row("2024_B_A", 2024, "B", "A", 11, 12, 2, 3, 1, 1),
    ]
    return events, features


class NFLV2JParallelValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.features = fixtures()

    def test_parallel_raw_evaluations_are_exact_and_in_original_order(self):
        serial = build_nfl_m2_v2j_raw_evaluations(self.events, self.features)
        parallel = build_nfl_m2_v2j_parallel_raw_evaluations(
            self.events,
            self.features,
            max_workers=2,
        )
        self.assertEqual(parallel, serial)
        self.assertEqual(
            [row["game_id"] for row in parallel],
            [row["game_id"] for row in serial],
        )

    def test_parallel_final_evidence_is_exactly_serial_evidence(self):
        kwargs = {
            "source_manifest_sha256": MANIFEST_SHA,
            "min_calibration_fit_seasons": 1,
            "calibration_bins": 2,
            "calibration_min_bin_n": 1,
        }
        serial = build_nfl_m2_v2j_candidate_evidence(
            self.events,
            self.features,
            **kwargs,
        )
        parallel = build_nfl_m2_v2j_parallel_candidate_evidence(
            self.events,
            self.features,
            max_workers=2,
            **kwargs,
        )
        self.assertEqual(parallel, serial)
        self.assertIs(parallel["promotion_authority"], False)
        self.assertIs(parallel["model_p_authority"], False)
        self.assertIs(parallel["official_status_granted"], False)
        self.assertIs(parallel["production_registry_consumes_this_artifact"], False)

    def test_contingency_does_not_modify_frozen_first_readout_entrypoint(self):
        script = (ROOT / "scripts/run_nfl_v2j_first_readout.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/nfl-v2j-first-readout.yml").read_text(encoding="utf-8")
        self.assertNotIn("m2_v2j_parallel_validation", script)
        self.assertNotIn("m2_v2j_parallel_validation", workflow)


if __name__ == "__main__":
    unittest.main()
