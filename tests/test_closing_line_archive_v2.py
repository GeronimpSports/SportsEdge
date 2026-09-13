import copy
import unittest
from datetime import datetime, timedelta, timezone

from scripts.capture_closing_line_archive_v2 import (
    START_GUARD_FAILURE_MODES,
    START_GUARD_SCHEDULED,
    build_rows,
    classify_events,
    load_policy,
    window_for,
    windows_for,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 12, 16, 0, tzinfo=UTC)
POLICY = load_policy("config/closing_line_archive_policy_v2.json")


def _event(minutes):
    return {
        "id": "e1",
        "commence_time": (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "home_team": "Home",
        "away_team": "Away",
        "bookmakers": [
            {
                "key": "draftkings",
                "last_update": "2026-09-12T15:59:00Z",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Home", "price": -110, "point": -3.5},
                            {"name": "Away", "price": -110, "point": 3.5},
                        ],
                    }
                ],
            }
        ],
    }


class WindowSemanticsTests(unittest.TestCase):
    def test_current_policy_membership(self):
        self.assertEqual(window_for(NOW + timedelta(minutes=6), NOW, POLICY), "close")
        self.assertEqual(windows_for(NOW + timedelta(minutes=6), NOW, POLICY), ("close",))
        self.assertEqual(window_for(NOW + timedelta(minutes=2), NOW, POLICY), "close")

    def test_t0_candidate_includes_exact_scheduled_t0_and_delay_grace(self):
        self.assertEqual(window_for(NOW, NOW, POLICY), "t0_candidate")
        self.assertEqual(window_for(NOW - timedelta(minutes=5), NOW, POLICY), "t0_candidate")
        self.assertEqual(window_for(NOW - timedelta(minutes=30), NOW, POLICY), "t0_candidate")
        self.assertIsNone(window_for(NOW - timedelta(minutes=30, seconds=1), NOW, POLICY))

    def test_overlap_is_multi_membership_not_priority_collapse(self):
        policy = copy.deepcopy(POLICY)
        policy["windows"]["t0_candidate"]["max_lead_minutes"] = 5
        policy["windows"]["t0_candidate"]["max_inclusive"] = True
        memberships = windows_for(NOW + timedelta(minutes=3), NOW, policy)
        self.assertEqual(memberships, ("close", "t0_candidate"))

        rows, skipped = build_rows(
            "americanfootball_nfl",
            [_event(3)],
            {"e1": memberships},
            NOW,
            policy,
        )
        self.assertFalse(skipped)
        self.assertEqual(len(rows), 4)
        close_rows = [row for row in rows if row["window"] == "close"]
        t0_rows = [row for row in rows if row["window"] == "t0_candidate"]
        self.assertEqual(len(close_rows), 2)
        self.assertEqual(len(t0_rows), 2)
        self.assertEqual({row["capture_id"] for row in rows}, {rows[0]["capture_id"]})
        self.assertEqual({row["fetch_sha256"] for row in rows}, {rows[0]["fetch_sha256"]})

    def test_rows_carry_start_guard_and_shared_fetch_identity(self):
        rows, skipped = build_rows(
            "baseball_mlb",
            [_event(-5)],
            {"e1": ("t0_candidate",)},
            NOW,
            POLICY,
        )
        self.assertFalse(skipped)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["capture_id"] for row in rows}), 1)
        self.assertEqual(len({row["fetch_sha256"] for row in rows}), 1)
        for row in rows:
            self.assertEqual(row["schema_version"], "CLOSING_LINE_ARCHIVE_ROW_V3")
            self.assertEqual(row["actual_start_status"], "UNADJUDICATED")
            self.assertTrue(row["requires_start_attestation"])
            self.assertEqual(row["start_guard"], START_GUARD_SCHEDULED)
            self.assertEqual(tuple(row["guard_failure_modes"]), START_GUARD_FAILURE_MODES)
            self.assertEqual(row["evidence_class"], "NOT_EVIDENCE")
            self.assertFalse(row["promotion_authority"])
            self.assertLess(row["scheduled_lead_minutes"], 0)

    def test_guard_rejection_names_early_and_late_start_failure_modes(self):
        expired = {
            "id": "expired",
            "commence_time": (NOW - timedelta(minutes=31)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        due, rejected = classify_events([expired], NOW, POLICY)
        self.assertFalse(due)
        self.assertEqual(len(rejected), 1)
        record = rejected[0]
        self.assertEqual(
            record["reason"],
            "SCHEDULED_COMMENCE_GUARD_EXPIRED_ACTUAL_START_UNKNOWN",
        )
        self.assertEqual(record["start_guard"], START_GUARD_SCHEDULED)
        self.assertIn(
            "ACTUAL_START_EARLIER_THAN_SCHEDULED_POST_START_ADMISSION_RISK",
            record["guard_failure_modes"],
        )
        self.assertIn(
            "ACTUAL_START_LATER_THAN_SCHEDULED_PRESTART_DATA_LOSS_RISK",
            record["guard_failure_modes"],
        )

    def test_priority_contract_covers_every_window_once(self):
        self.assertEqual(set(POLICY["window_priority"]), set(POLICY["windows"]))
        self.assertEqual(len(POLICY["window_priority"]), len(set(POLICY["window_priority"])))


if __name__ == "__main__":
    unittest.main()
