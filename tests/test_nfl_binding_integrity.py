from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT, PRODUCTION_NFL_M2_MODEL_ID
from sportsedge.sports.nfl.readiness import (
    NFLReadinessError,
    _validate_bettor_facing_odds_snapshot,
    run_nfl_ready,
)
from sportsedge.sports.nfl.run_machine import NFLMachineReport


HOME = "Chicago Bears"
AWAY = "Green Bay Packers"
CODE_SHA = "a" * 40
SOURCE_SHA = "b" * 64
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _event() -> dict:
    return {
        "id": "provider-event-1",
        "home_team": HOME,
        "away_team": AWAY,
        "bookmakers": [{
            "key": "draftkings",
            "title": "DraftKings",
            "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": HOME, "price": -125},
                    {"name": AWAY, "price": 105},
                ]},
                {"key": "spreads", "outcomes": [
                    {"name": HOME, "point": -2.5, "price": -110},
                    {"name": AWAY, "point": 2.5, "price": -110},
                ]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "point": 44.5, "price": -108},
                    {"name": "Under", "point": 44.5, "price": -112},
                ]},
            ],
        }],
    }


def _snapshot() -> dict:
    return {
        "source": "fixture",
        "observed_at": "2026-09-10T11:59:00+00:00",
        "events": [_event()],
    }


def _market(event: dict, key: str) -> dict:
    return next(row for row in event["bookmakers"][0]["markets"] if row["key"] == key)


def _validate(snapshot: dict) -> None:
    _validate_bettor_facing_odds_snapshot(snapshot, book_key="draftkings")


def _artifact() -> dict:
    return {"code_git_sha": CODE_SHA, "source_manifest_sha256": SOURCE_SHA}


def _registry() -> dict:
    return {
        "schema_version": 9,
        "sport": "nfl",
        "model_id": PRODUCTION_NFL_M2_MODEL_ID,
        "feature_contract": NFL_M2_FEATURE_CONTRACT,
        "code_git_sha": CODE_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "markets": {
            market: {"stage": "HISTORICAL_VALIDATION", "eligible": False}
            for market in ("moneyline", "spread", "total")
        },
    }


def _empty_report() -> NFLMachineReport:
    return NFLMachineReport(
        mode="AUTOMATIC",
        generated_at_utc=NOW.isoformat(),
        run_status="BLOCKED",
        machine_version="NFL_RUN_MACHINE_V1",
        results=(),
        summary={"quote_count": 0, "priced": 0, "stale": 0, "blocked": 0,
                 "official_bets": 0, "markets_seen": [], "games_seen": []},
        model_artifact_sha256="c" * 64,
        model_code_git_sha=CODE_SHA,
        training_source_manifest_sha256=SOURCE_SHA,
        live_feature_source_manifest_sha256="d" * 64,
        live_feature_asof_ts=NOW.isoformat(),
        quote_observed_at=NOW.isoformat(),
    )


class NFLBindingIntegrityTests(unittest.TestCase):
    def test_valid_exact_pairs_pass_readiness_guard(self):
        snapshot = _snapshot()
        self.assertIs(_validate_bettor_facing_odds_snapshot(snapshot, book_key="draftkings"), snapshot)

    def test_duplicate_moneyline_home_fails_before_binding(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "h2h")["outcomes"].append({"name": HOME, "price": -130})
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:h2h"):
            _validate(snapshot)

    def test_duplicate_spread_away_fails_before_binding(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "spreads")["outcomes"].append({"name": AWAY, "point": 2.5, "price": -115})
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:spreads"):
            _validate(snapshot)

    def test_duplicate_total_over_fails_before_binding(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "totals")["outcomes"].append({"name": "Over", "point": 44.5, "price": -105})
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:totals"):
            _validate(snapshot)

    def test_unexpected_moneyline_selection_fails_closed(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "h2h")["outcomes"][1] = {"name": "Tie", "price": 2500}
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_PAIR_MISMATCH:h2h"):
            _validate(snapshot)

    def test_unexpected_total_selection_fails_closed(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "totals")["outcomes"][1] = {"name": "Exact", "point": 44.5, "price": 500}
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_PAIR_MISMATCH:totals"):
            _validate(snapshot)

    def test_missing_pair_member_fails_closed(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "spreads")["outcomes"] = [_market(snapshot["events"][0], "spreads")["outcomes"][0]]
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:spreads"):
            _validate(snapshot)

    def test_duplicate_selected_book_fails_closed(self):
        snapshot = _snapshot()
        snapshot["events"][0]["bookmakers"].append(snapshot["events"][0]["bookmakers"][0].copy())
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_BOOKMAKER_COUNT_INVALID:draftkings"):
            _validate(snapshot)

    def test_duplicate_market_block_fails_closed(self):
        snapshot = _snapshot()
        snapshot["events"][0]["bookmakers"][0]["markets"].append(dict(_market(snapshot["events"][0], "totals")))
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_MARKET_COUNT_INVALID:totals"):
            _validate(snapshot)

    def test_manual_snapshot_is_rejected_before_frozen_machine_executes(self):
        snapshot = _snapshot()
        _market(snapshot["events"][0], "h2h")["outcomes"].append({"name": HOME, "price": -130})
        with patch("sportsedge.sports.nfl.readiness.run_nfl_machine") as engine:
            with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:h2h"):
                run_nfl_ready(
                    promotion_registry=_registry(), model_artifact=_artifact(),
                    expected_model_artifact_sha256="c" * 64,
                    runtime_code_git_sha=CODE_SHA, now=NOW,
                    odds_snapshot=snapshot, book_key="draftkings",
                )
            engine.assert_not_called()

    def test_automatic_fetcher_is_wrapped_before_frozen_machine_receives_it(self):
        bad = _snapshot()
        _market(bad["events"][0], "totals")["outcomes"].append({"name": "Over", "point": 44.5, "price": -105})
        with patch(
            "sportsedge.sports.nfl.readiness.run_nfl_machine",
            return_value=_empty_report(),
        ) as engine:
            run_nfl_ready(
                promotion_registry=_registry(), model_artifact=_artifact(),
                expected_model_artifact_sha256="c" * 64,
                runtime_code_git_sha=CODE_SHA, now=NOW,
                odds_fetcher=lambda: bad, book_key="draftkings",
            )
            wrapped = engine.call_args.kwargs["odds_fetcher"]
            with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_OUTCOME_COUNT_INVALID:totals"):
                wrapped()


if __name__ == "__main__":
    unittest.main()
