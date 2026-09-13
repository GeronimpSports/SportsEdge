import json
import unittest
from pathlib import Path

from sportsedge.sports.nfl.archive_adjudication import adjudicate_nfl_archive_row


ROOT = Path(__file__).resolve().parents[1]
GOV = json.loads((ROOT / "config/nfl_2026_prospective_governance_v1.json").read_text())
PBP = json.loads((ROOT / "config/research/nfl_play_level_research_generation_v1.json").read_text())
FLOORS = json.loads((ROOT / "config/truth_gate_floors.json").read_text())


class ProspectiveOwnershipTests(unittest.TestCase):
    def test_attempt9_exclusively_owns_clean_2026_confirmation(self):
        owner = GOV["prospective_season_owner"]
        self.assertEqual(owner["owner_candidate"]["selected_attempt"], 9)
        self.assertEqual(owner["owner_candidate"]["decay"], 0.85)
        self.assertEqual(owner["owner_status"], "ACTIVE_SINGLE_OWNER")
        self.assertIn("Only the frozen attempt-9", owner["exclusive_promotion_evidence_rule"])

    def test_2024_and_2025_are_exposed(self):
        exposed = set(GOV["historical_exposure"]["exposed_nonfinal_seasons"])
        self.assertIn(2024, exposed)
        self.assertIn(2025, exposed)
        self.assertFalse(GOV["historical_exposure"]["fresh_final_holdout_available_now"])

    def test_nfl_numeric_thresholds_are_precommitted(self):
        gates = GOV["nfl_game_market_precommitted_thresholds"]
        self.assertEqual(gates["minimum_model_edge_probability_points"], 0.03)
        self.assertEqual(gates["minimum_mean_clv_probability_points"], 0.005)
        self.assertEqual(gates["minimum_clv_t_stat"], 2.0)
        self.assertEqual(gates["minimum_after_vig_roi"], 0.02)
        self.assertEqual(gates["minimum_promoted_decisions"], 200)
        self.assertEqual(gates["minimum_distinct_week_clusters"], 12)
        self.assertEqual(gates["freeze_basis"], "PRE_2026_PROSPECTIVE_COLLECTION_POLICY; NOT DERIVED_FROM_2026_RESULTS")

    def test_precommit_does_not_fabricate_truth_gate_floor_provenance(self):
        floor_policy = FLOORS["truth_gate"]["floor_policy"]
        self.assertEqual(floor_policy["status"], "FROZEN_BEFORE_JUDGED_STREAM")
        self.assertEqual(
            floor_policy["derivation"],
            "PREREGISTERED_GOVERNANCE_MINIMUM_NOT_DERIVED_FROM_LATER_JUDGED_STREAM",
        )
        self.assertFalse(floor_policy["future_stream_may_lower_floor"])
        nfl_floors = FLOORS["truth_gate"]["edge_floors"]["NFL"]
        self.assertEqual(nfl_floors["moneyline"], 0.03)
        self.assertEqual(nfl_floors["spread"], 0.03)
        self.assertEqual(nfl_floors["game_total"], 0.03)
        relationship = GOV["nfl_game_market_precommitted_thresholds"]["truth_gate_floor_relationship"]
        self.assertIn("do not fabricate", relationship)
        self.assertIn("provenance-verified frozen edge floor", relationship)

    def test_play_level_generation_is_new_budget_and_2026_shadow_only(self):
        self.assertFalse(PBP["relationship_to_prior_search"]["extends_prior_budget"])
        self.assertEqual(PBP["relationship_to_prior_search"]["prior_attempts_spent"], 10)
        self.assertEqual(PBP["attempt_budget"]["maximum_candidate_attempts"], 5)
        self.assertFalse(PBP["data_windows"]["fresh_final_holdout_available"])
        self.assertIn("NOT_FINAL_HOLDOUT", PBP["data_windows"]["exposure_labels"]["2024"])
        self.assertIn("NOT_FRESH_FINAL_HOLDOUT", PBP["data_windows"]["exposure_labels"]["2025"])
        self.assertEqual(PBP["2026"]["this_generation_role"], "SHADOW_ONLY")
        self.assertFalse(PBP["2026"]["may_claim_clean_promotion_holdout"])


class ArchiveAdjudicationTests(unittest.TestCase):
    def _row(self, captured="2026-09-20T16:55:00Z", scheduled="2026-09-20T17:00:00Z"):
        return {
            "evidence_class": "NOT_EVIDENCE",
            "sport_key": "americanfootball_nfl",
            "event_id": "game-1",
            "captured_at": captured,
            "commence_time": scheduled,
        }

    def test_unknown_actual_start_fails_closed(self):
        out = adjudicate_nfl_archive_row(
            self._row(), actual_start_time=None, actual_start_source=None, actual_start_retrieved_at=None
        )
        self.assertEqual(out["adjudication"], "INCONCLUSIVE_ACTUAL_START_UNVERIFIED")
        self.assertFalse(out["pregame_actual_start_verified"])
        self.assertFalse(out["eligible_for_promotion_evidence"])

    def test_actual_start_before_capture_invalidates(self):
        out = adjudicate_nfl_archive_row(
            self._row(),
            actual_start_time="2026-09-20T16:54:00Z",
            actual_start_source="source://actual-start",
            actual_start_retrieved_at="2026-09-20T20:00:00Z",
        )
        self.assertEqual(out["adjudication"], "INVALID_CAPTURE_AT_OR_AFTER_ACTUAL_START")
        self.assertFalse(out["pregame_actual_start_verified"])

    def test_actual_start_cannot_rescue_scheduled_poststart_capture(self):
        out = adjudicate_nfl_archive_row(
            self._row(captured="2026-09-20T17:01:00Z", scheduled="2026-09-20T17:00:00Z"),
            actual_start_time="2026-09-20T17:05:00Z",
            actual_start_source="source://actual-start",
            actual_start_retrieved_at="2026-09-20T20:00:00Z",
        )
        self.assertEqual(out["adjudication"], "INVALID_SCHEDULED_WINDOW_CANNOT_BE_RESCUED")
        self.assertFalse(out["can_rescue_missed_or_out_of_window_capture"])
        self.assertFalse(out["eligible_for_promotion_evidence"])

    def test_confirmed_pregame_is_still_archive_only(self):
        out = adjudicate_nfl_archive_row(
            self._row(),
            actual_start_time="2026-09-20T17:02:00Z",
            actual_start_source="source://actual-start",
            actual_start_retrieved_at="2026-09-20T20:00:00Z",
        )
        self.assertTrue(out["pregame_actual_start_verified"])
        self.assertEqual(out["adjudication"], "PREGAME_ACTUAL_START_CONFIRMED_ARCHIVE_ONLY")
        self.assertFalse(out["eligible_for_promotion_evidence"])
        self.assertFalse(out["creates_model_p"])
        self.assertFalse(out["creates_decision_row"])


if __name__ == "__main__":
    unittest.main()
