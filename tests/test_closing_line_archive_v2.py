import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts import capture_closing_line_archive_v2 as v2

UTC = timezone.utc
POLICY = {
    "windows": {
        "t0_prestart": {"min_minutes_before_start": 0, "max_minutes_before_start": 5},
        "close": {"min_minutes_before_start": 2, "max_minutes_before_start": 20},
        "decision": {"min_minutes_before_start": 45, "max_minutes_before_start": 120},
    }
}


class ClosingLineArchiveV2Tests(unittest.TestCase):
    def test_close_wins_overlap_with_t0(self):
        now = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)
        start = datetime(2026, 9, 13, 18, 4, tzinfo=UTC)
        self.assertEqual(v2.prioritized_window_for(start, now, POLICY), "close")

    def test_nonpositive_lead_is_rejected(self):
        now = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)
        self.assertIsNone(v2.prioritized_window_for(now, now, POLICY))

    def test_mlb_guard_blocks_when_first_play_exists(self):
        event = {"home_team": "Chicago Cubs", "away_team": "Milwaukee Brewers", "commence_time": "2026-09-13T18:10:00Z"}
        schedule_game = {"status": {"abstractGameState": "Preview"}}
        feed = {
            "gameData": {"status": {"abstractGameState": "Live"}},
            "liveData": {"plays": {"allPlays": [{"about": {"startTime": "2026-09-13T18:11:03Z"}}]}},
        }
        with patch.object(v2, "_mlb_match", return_value=(123, schedule_game)), patch.object(v2, "_get_json", return_value=feed):
            got = v2.mlb_actual_start_guard(event)
        self.assertTrue(got["known"])
        self.assertTrue(got["started"])
        self.assertEqual(got["reason"], "MLB_ALREADY_STARTED")

    def test_mlb_guard_fails_closed_on_ambiguous_identity(self):
        event = {"home_team": "Chicago Cubs", "away_team": "Milwaukee Brewers", "commence_time": "2026-09-13T18:10:00Z"}
        with patch.object(v2, "_mlb_match", return_value=None):
            got = v2.mlb_actual_start_guard(event)
        self.assertFalse(got["known"])
        self.assertIsNone(got["started"])
        self.assertEqual(got["reason"], "MLB_STATSAPI_EVENT_IDENTITY_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
