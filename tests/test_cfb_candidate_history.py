import unittest

from sportsedge.sports.cfb.candidate_history import enrich_candidate_history
from sportsedge.sports.cfb.source import CFBTeamMetrics


def metric(team, season, through_week, source, value):
    return CFBTeamMetrics(
        team=team, season=season, through_week=through_week, sample_source=source,
        off_ppa_rush=value, off_ppa_dropback=value,
        def_ppa_rush_allowed=value, def_ppa_dropback_allowed=value,
        off_success_rate=value, def_success_rate_allowed=value,
        standard_down_ppa=value, passing_down_success_rate=value,
        eckel_rate=value, points_per_eckel=value, points_per_drive=value,
        net_field_position=value, explosive_rate=value,
        feature_asof_ts="2026-01-01T00:00:00+00:00",
    )


class TestCFBCandidateHistory(unittest.TestCase):
    def test_enrichment_is_schedule_counted_and_score_blind(self):
        rows = [
            {"game_id":"g1","season":2026,"week":1,"home_metrics":{"team":"A"},"away_metrics":{"team":"B"},"home_score":100,"away_score":0},
            {"game_id":"g2","season":2026,"week":2,"home_metrics":{"team":"A"},"away_metrics":{"team":"C"},"home_score":0,"away_score":100},
        ]
        metrics = [
            metric("A",2025,99,"PRIOR_SEASON_FALLBACK",1.0),
            metric("B",2025,99,"PRIOR_SEASON_FALLBACK",1.0),
            metric("C",2025,99,"PRIOR_SEASON_FALLBACK",1.0),
            metric("A",2026,1,"CURRENT_SEASON_PRIOR_WEEKS",2.0),
            metric("C",2026,1,"CURRENT_SEASON_PRIOR_WEEKS",2.0),
        ]
        out = enrich_candidate_history(rows, metrics=metrics)
        self.assertEqual(out[0]["home_current_metrics"]["games_in_sample"], 0)
        self.assertEqual(out[1]["home_current_metrics"]["games_in_sample"], 1)
        self.assertEqual(out[1]["away_current_metrics"]["games_in_sample"], 0)
        self.assertEqual(out[1]["home_prior_metrics"]["season"], 2025)
        self.assertEqual(out[1]["home_current_metrics"]["season"], 2026)

    def test_missing_exact_current_snapshot_fails_closed(self):
        rows = [{"game_id":"g","season":2026,"week":2,"home_metrics":{"team":"A"},"away_metrics":{"team":"B"}}]
        metrics = [
            metric("A",2025,99,"PRIOR_SEASON_FALLBACK",1.0),
            metric("B",2025,99,"PRIOR_SEASON_FALLBACK",1.0),
        ]
        with self.assertRaisesRegex(ValueError, "CURRENT_MISSING"):
            enrich_candidate_history(rows, metrics=metrics)


if __name__ == "__main__":
    unittest.main()
