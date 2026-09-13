import unittest

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT
from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from sportsedge.sports.nfl.m2_v2j_runtime_shard import (
    NFLV2JShardError,
    build_v2j_candidate_evidence_from_raw_exact,
    build_v2j_raw_evaluation_shard,
    merge_v2j_raw_evaluation_shards,
)
from sportsedge.sports.nfl.m2_v2j_validation import (
    build_nfl_m2_v2j_candidate_evidence,
    build_nfl_m2_v2j_raw_evaluations,
)

MANIFEST = "a" * 64
CODE_SHA = "b" * 40


def feature(shift, qb):
    return {
        "feature_contract": NFL_M2_FEATURE_CONTRACT,
        "qb_id": qb,
        "feature_asof_ts": "2026-09-01T12:00:00+00:00",
        "adj_off_epa": 0.10 + shift,
        "adj_def_epa": -0.02 - shift,
        "pass_epa": 0.12 + shift,
        "rush_epa": 0.01 + shift,
        "pressure_for": 0.30 + shift * 0.1,
        "pressure_allowed": 0.25 - shift * 0.1,
        "success_rate": 0.44 + shift * 0.1,
        "explosive_rate": 0.11 + shift * 0.05,
        "rest_diff_days": 1.0,
        "travel_miles": 300.0,
        "timezone_crossings": 0.0,
        "short_week": 0.0,
        "bye_week": 0.0,
        "wind_mph": 5.0,
        "roof_closed": 0.0,
        "qb_adjustment": shift,
        "prior_efficiency": 0.02 + shift,
        "prior_weight": 0.4,
    }


def event(game_id, season, home, away, hd, ad, htd, atd, hfg, afg):
    return {
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "game_id": game_id,
        "season": season,
        "home_team": home,
        "away_team": away,
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
    events = []
    features = []
    specs = {
        2020: [("A", "B", 10, 11, 3, 2, 2, 1, 27, 20), ("B", "A", 11, 10, 2, 2, 1, 2, 23, 21)],
        2021: [("A", "B", 12, 10, 2, 2, 2, 1, 26, 17), ("B", "A", 10, 12, 2, 3, 1, 1, 20, 28)],
        2022: [("A", "B", 11, 12, 3, 1, 1, 2, 30, 16), ("B", "A", 12, 11, 2, 2, 2, 1, 24, 23)],
        2023: [("A", "B", 10, 10, 2, 2, 1, 1, 21, 20), ("B", "A", 11, 12, 2, 3, 1, 1, 19, 27)],
    }
    for season, games in specs.items():
        for index, spec in enumerate(games, start=1):
            home, away, hd, ad, htd, atd, hfg, afg, hs, aws = spec
            game_id = f"{season}_0{index}_{away}_{home}"
            events.append(event(game_id, season, home, away, hd, ad, htd, atd, hfg, afg))
            shift = 0.04 * (season - 2020) + (0.03 if index == 1 else -0.02)
            features.append({
                "game_id": game_id,
                "season": season,
                "week": index,
                "home_team": home,
                "away_team": away,
                "home_features": feature(shift, f"H{season}{index}"),
                "away_features": feature(-shift, f"A{season}{index}"),
                "home_score": hs,
                "away_score": aws,
                "spread_line": -2.5 if index == 1 else 1.5,
                "total_line": 44.5,
                "home_spread_odds": -110,
                "away_spread_odds": -110,
                "over_odds": -108,
                "under_odds": -112,
            })
    return events, features


class NFLV2JRuntimeShardTests(unittest.TestCase):
    def test_two_way_shards_merge_to_exact_unsharded_raw_rows_and_evidence(self):
        events, features = fixtures()
        reference_raw = build_nfl_m2_v2j_raw_evaluations(events, features, min_train_seasons=2)
        shards = []
        for season in (2022, 2023):
            for shard_index in range(2):
                shards.append(build_v2j_raw_evaluation_shard(
                    events,
                    features,
                    test_season=season,
                    shard_index=shard_index,
                    shard_count=2,
                    source_manifest_sha256=MANIFEST,
                    code_git_sha=CODE_SHA,
                    min_train_seasons=2,
                ))
        merged = merge_v2j_raw_evaluation_shards(shards)
        self.assertEqual(merged, reference_raw)

        reference_evidence = build_nfl_m2_v2j_candidate_evidence(
            events,
            features,
            source_manifest_sha256=MANIFEST,
            min_train_seasons=2,
        )
        merged_evidence = build_v2j_candidate_evidence_from_raw_exact(
            merged,
            source_manifest_sha256=MANIFEST,
            min_train_seasons=2,
        )
        self.assertEqual(merged_evidence, reference_evidence)

    def test_missing_shard_fails_closed(self):
        events, features = fixtures()
        shard = build_v2j_raw_evaluation_shard(
            events,
            features,
            test_season=2022,
            shard_index=0,
            shard_count=2,
            source_manifest_sha256=MANIFEST,
            code_git_sha=CODE_SHA,
        )
        with self.assertRaisesRegex(NFLV2JShardError, "SHARD_SET_INCOMPLETE"):
            merge_v2j_raw_evaluation_shards([shard])

    def test_duplicate_test_index_fails_closed(self):
        events, features = fixtures()
        shard0 = build_v2j_raw_evaluation_shard(
            events, features, test_season=2022, shard_index=0, shard_count=2,
            source_manifest_sha256=MANIFEST, code_git_sha=CODE_SHA,
        )
        shard1 = build_v2j_raw_evaluation_shard(
            events, features, test_season=2022, shard_index=1, shard_count=2,
            source_manifest_sha256=MANIFEST, code_git_sha=CODE_SHA,
        )
        shard1["rows"] = list(shard1["rows"]) + [dict(shard0["rows"][0])]
        with self.assertRaisesRegex(NFLV2JShardError, "DUPLICATE_TEST_INDEX"):
            merge_v2j_raw_evaluation_shards([shard0, shard1])

    def test_identity_drift_fails_closed(self):
        events, features = fixtures()
        shard0 = build_v2j_raw_evaluation_shard(
            events, features, test_season=2022, shard_index=0, shard_count=2,
            source_manifest_sha256=MANIFEST, code_git_sha=CODE_SHA,
        )
        shard1 = build_v2j_raw_evaluation_shard(
            events, features, test_season=2022, shard_index=1, shard_count=2,
            source_manifest_sha256="c" * 64, code_git_sha=CODE_SHA,
        )
        with self.assertRaisesRegex(NFLV2JShardError, "IDENTITY_DRIFT"):
            merge_v2j_raw_evaluation_shards([shard0, shard1])


if __name__ == "__main__":
    unittest.main()
