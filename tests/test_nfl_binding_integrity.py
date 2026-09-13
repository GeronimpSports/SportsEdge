from __future__ import annotations

from copy import deepcopy
import unittest

from sportsedge.sports.nfl.run_machine import NFLRunMachineError, _event_quotes


HOME = "Chicago Bears"
AWAY = "Green Bay Packers"


def _game() -> dict:
    return {
        "home_team": "CHI",
        "away_team": "GB",
        "provider_home_team": HOME,
        "provider_away_team": AWAY,
    }


def _event() -> dict:
    return {
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


def _market(event: dict, key: str) -> dict:
    return next(row for row in event["bookmakers"][0]["markets"] if row["key"] == key)


class NFLBindingIntegrityTests(unittest.TestCase):
    def test_valid_exact_pairs_still_produce_six_quotes(self):
        quotes, book = _event_quotes(_game(), _event(), book_key="draftkings")
        self.assertEqual(book, "DraftKings")
        self.assertEqual(len(quotes), 6)
        self.assertEqual({row["market"] for row in quotes}, {"MONEYLINE", "SPREAD", "TOTAL"})

    def test_duplicate_moneyline_home_fails_before_binding(self):
        event = _event()
        _market(event, "h2h")["outcomes"].append({"name": HOME, "price": -130})
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_MONEYLINE_OUTCOME_COUNT_INVALID"):
            _event_quotes(_game(), event, book_key="draftkings")

    def test_duplicate_spread_away_fails_before_binding(self):
        event = _event()
        _market(event, "spreads")["outcomes"].append({"name": AWAY, "point": 2.5, "price": -115})
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_SPREAD_OUTCOME_COUNT_INVALID"):
            _event_quotes(_game(), event, book_key="draftkings")

    def test_duplicate_total_over_fails_before_binding(self):
        event = _event()
        _market(event, "totals")["outcomes"].append({"name": "Over", "point": 44.5, "price": -105})
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_TOTAL_OUTCOME_COUNT_INVALID"):
            _event_quotes(_game(), event, book_key="draftkings")

    def test_unexpected_moneyline_selection_fails_closed(self):
        event = _event()
        _market(event, "h2h")["outcomes"][1] = {"name": "Tie", "price": 2500}
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_MONEYLINE_OUTCOME_UNEXPECTED:Tie"):
            _event_quotes(_game(), event, book_key="draftkings")

    def test_unexpected_total_selection_fails_closed(self):
        event = _event()
        _market(event, "totals")["outcomes"][1] = {"name": "Exact", "point": 44.5, "price": 500}
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_TOTAL_OUTCOME_UNEXPECTED:Exact"):
            _event_quotes(_game(), event, book_key="draftkings")

    def test_missing_pair_member_fails_closed(self):
        event = _event()
        _market(event, "spreads")["outcomes"] = [_market(event, "spreads")["outcomes"][0]]
        with self.assertRaisesRegex(NFLRunMachineError, "NFL_SPREAD_OUTCOME_COUNT_INVALID"):
            _event_quotes(_game(), event, book_key="draftkings")


if __name__ == "__main__":
    unittest.main()
