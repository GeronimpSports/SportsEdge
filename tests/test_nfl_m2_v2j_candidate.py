import unittest

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT
from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2j_candidate import (
    NFL_M2_V2J_CANDIDATE_MODEL_ID,
    conditioned_drive_probabilities,
    fit_nfl_m2_v2j_candidate,
)


def feature(team_shift=0.0):
    values = {
        "feature_contract": NFL_M2_FEATURE_CONTRACT,
        "qb_id": "QB1",
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
    return values


def event(home, away, season, hd, ad, htd, atd, hfg, afg):
    return {
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "home_team": home, "away_team": away, "season": season,
        "home_drives": hd, "away_drives": ad,
        "home_td_xp_good": htd, "away_td_xp_good": atd,
        "home_td_xp_miss": 0, "away_td_xp_miss": 0,
        "home_td_two_good": 0, "away_td_two_good": 0,
        "home_td_two_fail": 0, "away_td_two_fail": 0,
        "home_field_goals": hfg, "away_field_goals": afg,
        "home_other_no_score": hd - htd - hfg,
        "away_other_no_score": ad - atd - afg,
        "home_safeties": 0, "away_safeties": 0,
    }


class NFLM2V2JCandidateTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            event("A", "B", 2023, 10, 11, 3, 2, 2, 1),
            event("B", "A", 2023, 12, 10, 2, 2, 2, 1),
            event("A", "B", 2024, 11, 12, 3, 1, 1, 2),
            event("B", "A", 2024, 10, 10, 2, 2, 1, 1),
        ]
        self.features = [
            {"home_features": feature(0.2), "away_features": feature(-0.2), "home_score": 27, "away_score": 17},
            {"home_features": feature(-0.1), "away_features": feature(0.1), "home_score": 20, "away_score": 23},
            {"home_features": feature(0.3), "away_features": feature(-0.3), "home_score": 30, "away_score": 16},
            {"home_features": feature(-0.2), "away_features": feature(0.2), "home_score": 17, "away_score": 24},
        ]

    def test_fit_uses_separate_identity_and_shared_environment(self):
        model = fit_nfl_m2_v2j_candidate(self.events, self.features)
        self.assertEqual(model.model_id, NFL_M2_V2J_CANDIDATE_MODEL_ID)
        self.assertTrue(model.shared_environment)
        self.assertAlmostEqual(sum(weight for _, weight in model.shared_environment), 1.0)

    def test_market_fields_are_rejected(self):
        contaminated = [dict(row) for row in self.features]
        contaminated[0] = dict(contaminated[0])
        contaminated[0]["home_features"] = dict(contaminated[0]["home_features"])
        contaminated[0]["home_features"]["spread_line"] = -3.5
        with self.assertRaisesRegex(ValueError, "MARKET_DATA_PROHIBITED"):
            fit_nfl_m2_v2j_candidate(self.events, contaminated)

    def test_conditioning_and_shared_environment_change_drive_probability(self):
        model = fit_nfl_m2_v2j_candidate(self.events, self.features)
        neutral = conditioned_drive_probabilities(
            model, offense="A", defense="B",
            offense_features=feature(0.0), defense_features=feature(0.0), shared_environment=0.0,
        )
        strong = conditioned_drive_probabilities(
            model, offense="A", defense="B",
            offense_features=feature(0.4), defense_features=feature(-0.4), shared_environment=0.5,
        )
        self.assertAlmostEqual(sum(neutral.values()), 1.0)
        self.assertAlmostEqual(sum(strong.values()), 1.0)
        self.assertNotEqual(neutral, strong)

    def test_market_mutation_cannot_change_clean_model(self):
        model = fit_nfl_m2_v2j_candidate(self.events, self.features)
        clean = conditioned_drive_probabilities(
            model, offense="A", defense="B",
            offense_features=feature(0.2), defense_features=feature(-0.2), shared_environment=0.0,
        )
        dirty = feature(0.2)
        dirty["closing_total"] = 47.5
        with self.assertRaisesRegex(ValueError, "MARKET_DATA_PROHIBITED"):
            conditioned_drive_probabilities(
                model, offense="A", defense="B",
                offense_features=dirty, defense_features=feature(-0.2), shared_environment=0.0,
            )
        self.assertAlmostEqual(sum(clean.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
