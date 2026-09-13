import unittest
from datetime import datetime, timedelta, timezone

from scripts.capture_closing_line_archive_v2 import build_rows, load_policy, window_for

UTC = timezone.utc
NOW = datetime(2026, 9, 12, 16, 0, tzinfo=UTC)
POLICY = load_policy("config/closing_line_archive_policy_v2.json")


def _event(minutes):
    return {
        "id": "e1",
        "commence_time": (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [{"key": "draftkings", "last_update": "2026-09-12T15:59:00Z", "markets": [{"key": "spreads", "outcomes": [{"name": "Home", "price": -110, "point": -3.5}, {"name": "Away", "price": -110, "point": 3.5}]}]}],
    }


class WindowSemanticsTests(unittest.TestCase):
    def test_overlap_is_explicit_close_priority(self):
        self.assertEqual(window_for(NOW + timedelta(minutes=6), NOW, POLICY), "close")
        self.assertEqual(window_for(NOW + timedelta(minutes=5), NOW, POLICY), "close")
        self.assertEqual(window_for(NOW + timedelta(minutes=2.5), NOW, POLICY), "close")
        self.assertEqual(window_for(NOW + timedelta(minutes=2), NOW, POLICY), "close")

    def test_t0_candidate_includes_exact_scheduled_t0_and_delay_grace(self):
        self.assertEqual(window_for(NOW, NOW, POLICY), "t0_candidate")
        self.assertEqual(window_for(NOW - timedelta(minutes=5), NOW, POLICY), "t0_candidate")
        self.assertEqual(window_for(NOW - timedelta(minutes=30), NOW, POLICY), "t0_candidate")
        self.assertIsNone(window_for(NOW - timedelta(minutes=30, seconds=1), NOW, POLICY))

    def test_rows_never_claim_prestart_without_attestation(self):
        rows, skipped = build_rows("baseball_mlb", [_event(-5)], {"e1": "t0_candidate"}, NOW, POLICY)
        self.assertFalse(skipped)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["actual_start_status"], "UNADJUDICATED")
            self.assertTrue(row["requires_start_attestation"])
            self.assertEqual(row["evidence_class"], "NOT_EVIDENCE")
            self.assertFalse(row["promotion_authority"])
            self.assertLess(row["scheduled_lead_minutes"], 0)

    def test_priority_contract_covers_every_window_once(self):
        self.assertEqual(set(POLICY["window_priority"]), set(POLICY["windows"]))
        self.assertEqual(len(POLICY["window_priority"]), len(set(POLICY["window_priority"])))


if __name__ == "__main__":
    unittest.main()
