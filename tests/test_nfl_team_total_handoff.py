from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
import unittest

from sportsedge.sports.nfl.run_machine import run_nfl_machine
from sportsedge.sports.nfl.team_total_handoff import (
    NFLTeamTotalHandoffError,
    build_team_total_distribution_handoff,
    verify_handoff_against_canonical_report,
)
from tests.test_nfl_run_machine import (
    CODE_SHA,
    NOW,
    _artifact,
    _artifact_hash,
    _live,
    _odds,
)


def _handoff(artifact: dict | None = None, live: dict | None = None) -> dict:
    bound = _artifact() if artifact is None else artifact
    return build_team_total_distribution_handoff(
        model_artifact=bound,
        expected_model_artifact_sha256=_artifact_hash(bound),
        runtime_code_git_sha=CODE_SHA,
        live_features=_live() if live is None else live,
        now=NOW,
    )


def _report(*, artifact: dict | None = None, live: dict | None = None, odds: dict | None = None):
    bound = _artifact() if artifact is None else artifact
    return run_nfl_machine(
        mode="MANUAL",
        model_artifact=bound,
        expected_model_artifact_sha256=_artifact_hash(bound),
        runtime_code_git_sha=CODE_SHA,
        now=NOW,
        live_features=_live() if live is None else live,
        odds_snapshot=_odds() if odds is None else odds,
    )


class NFLTeamTotalHandoffTests(unittest.TestCase):
    def test_build_api_has_no_sportsbook_line_or_price_input(self):
        params = set(inspect.signature(build_team_total_distribution_handoff).parameters)
        forbidden = {"odds", "odds_snapshot", "book_key", "spread", "total", "line", "price"}
        self.assertFalse(params & forbidden)

    def test_pre_odds_handoff_matches_canonical_run_machine_distribution_exactly(self):
        artifact = _artifact()
        handoff = _handoff(artifact)
        report = _report(artifact=artifact)
        verified = verify_handoff_against_canonical_report(handoff, report)
        self.assertTrue(verified["canonical_distribution_match"])
        self.assertTrue(verified["sportsbook_data_was_excluded_from_handoff_build"])
        self.assertFalse(verified["promotion_authority"])
        self.assertFalse(verified["model_p_authority"])
        self.assertFalse(verified["staking_authority"])
        self.assertFalse(verified["official_authority"])
        self.assertEqual(
            verified["games"][0]["distribution_sha256"],
            report.results[0].distribution_sha256,
        )

    def test_market_lines_change_readouts_not_pre_odds_distribution_identity(self):
        artifact = _artifact()
        handoff = _handoff(artifact)
        report_a = _report(artifact=artifact, odds=_odds(spread=-2.5, total=44.5))
        report_b = _report(artifact=artifact, odds=_odds(spread=-6.5, total=51.5))
        sha = handoff["games"][0]["distribution_sha256"]
        self.assertEqual({row.distribution_sha256 for row in report_a.results}, {sha})
        self.assertEqual({row.distribution_sha256 for row in report_b.results}, {sha})
        verify_handoff_against_canonical_report(handoff, report_a)
        verify_handoff_against_canonical_report(handoff, report_b)

    def test_tampered_score_rows_fail_self_hash_before_derivative_use(self):
        handoff = _handoff()
        report = _report()
        tampered = deepcopy(handoff)
        tampered["games"][0]["score_rows"][0]["home_score"] += 1
        with self.assertRaisesRegex(
            NFLTeamTotalHandoffError,
            "NFL_TEAM_TOTAL_HANDOFF_SELF_HASH_MISMATCH",
        ):
            verify_handoff_against_canonical_report(tampered, report)

    def test_report_distribution_mismatch_fails_canonical_binding(self):
        handoff = _handoff()
        report = _report()
        changed = tuple(
            replace(row, distribution_sha256="d" * 64)
            for row in report.results
        )
        bad_report = replace(report, results=changed)
        with self.assertRaisesRegex(
            NFLTeamTotalHandoffError,
            "NFL_TEAM_TOTAL_HANDOFF_CANONICAL_HASH_MISMATCH",
        ):
            verify_handoff_against_canonical_report(handoff, bad_report)

    def test_live_feature_provenance_mismatch_fails(self):
        handoff = _handoff()
        report = _report()
        bad = deepcopy(handoff)
        bad["live_feature_source_manifest_sha256"] = "e" * 64
        with self.assertRaisesRegex(
            NFLTeamTotalHandoffError,
            "NFL_TEAM_TOTAL_HANDOFF_IDENTITY_MISMATCH:live_feature_source_manifest_sha256",
        ):
            verify_handoff_against_canonical_report(bad, report)

    def test_authority_cannot_be_smuggled_into_handoff(self):
        report = _report()
        for field in (
            "promotion_authority",
            "model_p_authority",
            "staking_authority",
            "official_authority",
            "sportsbook_data_consumed",
            "market_line_consumed",
            "market_price_consumed",
            "model_fit_performed",
        ):
            handoff = _handoff()
            handoff[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(
                NFLTeamTotalHandoffError,
                "NFL_TEAM_TOTAL_HANDOFF_ZERO_AUTHORITY_REQUIRED",
            ):
                verify_handoff_against_canonical_report(handoff, report)

    def test_model_artifact_hash_mismatch_fails_before_distribution_build(self):
        artifact = _artifact()
        with self.assertRaisesRegex(
            NFLTeamTotalHandoffError,
            "NFL_MODEL_ARTIFACT_SHA256_MISMATCH",
        ):
            build_team_total_distribution_handoff(
                model_artifact=artifact,
                expected_model_artifact_sha256="f" * 64,
                runtime_code_git_sha=CODE_SHA,
                live_features=_live(),
                now=NOW,
            )

    def test_stale_live_features_fail_before_distribution_build(self):
        live = _live()
        live["asof_ts"] = "2026-09-10T09:00:00+00:00"
        with self.assertRaisesRegex(
            NFLTeamTotalHandoffError,
            "NFL_LIVE_FEATURE_SNAPSHOT_STALE",
        ):
            _handoff(live=live)


if __name__ == "__main__":
    unittest.main()
