from __future__ import annotations

import unittest

from sportsedge.sports.nfl.readiness import (
    NFLReadinessError,
    _validate_bettor_facing_odds_snapshot,
)


HOME = "Chicago Bears"
AWAY = "Green Bay Packers"


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
        snapshot["events"][0]["bookmakers"][0]["markets"].append(
            dict(_market(snapshot["events"][0], "totals"))
        )
        with self.assertRaisesRegex(NFLReadinessError, "NFL_BINDING_MARKET_COUNT_INVALID:totals"):
            _validate(snapshot)


if __name__ == "__main__":
    unittest.main()
