from pathlib import Path
import unittest

from sportsedge.sports.nfl.m2_v2g_candidate import NFL_M2_V2G_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2g_validation import build_nfl_m2_v2g_raw_evaluations


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/nfl-v2g-source-bound-artifact.yml"


def _row(season, week, *, spread=3.0, total=44.0):
    return {
        "event_contract": NFL_M2_V2G_EVENT_CONTRACT,
        "game_id": f"{season}_{week}_B_A",
        "season": season,
        "week": week,
        "home_team": "A",
        "away_team": "B",
        "home_drives": 10,
        "home_touchdowns": 3 if week % 2 else 2,
        "home_field_goals": 1,
        "home_other_no_score": 6 if week % 2 else 7,
        "away_drives": 10,
        "away_touchdowns": 2,
        "away_field_goals": 2 if week % 2 else 1,
        "away_other_no_score": 6 if week % 2 else 7,
        "home_score": 24 if week % 2 else 20,
        "away_score": 20 if week % 2 else 17,
        "spread_line": spread,
        "total_line": total,
        "home_spread_odds": -110,
        "away_spread_odds": -110,
        "over_odds": -110,
        "under_odds": -110,
    }


class NFLV2GHistoricalDiagnosticTests(unittest.TestCase):
    def test_market_thresholds_do_not_change_v2g_distribution_profile(self):
        base = [_row(season, week) for season in (2020, 2021, 2022) for week in (1, 2)]
        shifted = [dict(row) for row in base]
        for row in shifted:
            if row["season"] == 2022:
                row["spread_line"] = 9.5
                row["total_line"] = 61.5
                row["home_spread_odds"] = 175
                row["away_spread_odds"] = -210
                row["over_odds"] = 150
                row["under_odds"] = -180

        left = build_nfl_m2_v2g_raw_evaluations(base, min_train_seasons=2)
        right = build_nfl_m2_v2g_raw_evaluations(shifted, min_train_seasons=2)
        self.assertTrue(left)
        self.assertEqual(len(left), len(right))
        for a, b in zip(left, right):
            self.assertEqual(a["candidate_signed_key_probability"], b["candidate_signed_key_probability"])

    def test_workflow_keeps_frozen_gate_and_zero_authority(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--max-abs-error 0.005", text)
        self.assertIn("NFL_V2G_PROMOTION_AUTHORITY_FORBIDDEN", text)
        self.assertIn("NFL_V2G_MODEL_P_AUTHORITY_FORBIDDEN", text)
        self.assertIn("NFL_PROPS_MUST_REMAIN_NO_ENGINE", text)
        self.assertIn("run_nfl_v2g_historical_diagnostic.py", text)
        self.assertIn("validate_nfl_v2g_candidate.py", text)


if __name__ == "__main__":
    unittest.main()
