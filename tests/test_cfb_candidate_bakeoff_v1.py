import unittest
from unittest.mock import patch

from sportsedge.sports.cfb import candidate_bakeoff_v1 as bakeoff


class TestCFBCandidateBakeoffV1(unittest.TestCase):
    def test_real_execution_requires_explicit_four_attempt_authorization(self):
        with self.assertRaisesRegex(ValueError, "EXPLICIT_FOUR_ATTEMPT_AUTHORIZATION_REQUIRED"):
            bakeoff.run_frozen_four_candidate_bakeoff(
                [], authorization="NO", prereg_binding={}, acquisition_readiness={}, seed_material="x"
            )

    def test_acquisition_gate_blocks_before_any_candidate_evaluation(self):
        with patch.object(bakeoff, "evaluate_candidate") as evaluate:
            with self.assertRaisesRegex(ValueError, "ACQUISITION_NOT_READY"):
                bakeoff.run_frozen_four_candidate_bakeoff(
                    [],
                    authorization=bakeoff.ATTEMPT_AUTHORIZATION,
                    prereg_binding={"status":"READY_FOR_FIRST_EVALUATION","attempts_consumed":0},
                    acquisition_readiness={"status":"BLOCKED_ACQUISITION_NOT_VERIFIED"},
                    seed_material="x",
                )
            evaluate.assert_not_called()

    def test_prereg_gate_blocks_before_any_candidate_evaluation(self):
        with patch.object(bakeoff, "evaluate_candidate") as evaluate:
            with self.assertRaisesRegex(ValueError, "PREREG_BINDING_NOT_READY"):
                bakeoff.run_frozen_four_candidate_bakeoff(
                    [],
                    authorization=bakeoff.ATTEMPT_AUTHORIZATION,
                    prereg_binding={"status":"BLOCKED"},
                    acquisition_readiness={"status":"READY_FOR_HISTORICAL_REPLAY"},
                    seed_material="x",
                )
            evaluate.assert_not_called()

    def test_null_control_cannot_silently_use_fewer_than_200_shuffles(self):
        with self.assertRaisesRegex(ValueError, "NULL_SHUFFLE_COUNT_MUST_BE_200"):
            bakeoff.run_null_control([], seed_material="x", shuffle_count=199)

    def test_label_shuffle_preserves_paired_scores_within_season(self):
        rows = [
            {"season":2024,"home_score":10,"away_score":7,"id":"a"},
            {"season":2024,"home_score":30,"away_score":20,"id":"b"},
            {"season":2025,"home_score":14,"away_score":13,"id":"c"},
        ]
        out = bakeoff._shuffle_labels(rows, rng=__import__("numpy").random.default_rng(7))
        pairs_2024 = sorted((r["home_score"],r["away_score"]) for r in out if r["season"]==2024)
        self.assertEqual(pairs_2024, [(10,7),(30,20)])
        self.assertEqual([(r["home_score"],r["away_score"]) for r in out if r["season"]==2025], [(14,13)])

    def test_seed_is_deterministic_and_shuffle_specific(self):
        self.assertEqual(bakeoff._seed("binding", 1), bakeoff._seed("binding", 1))
        self.assertNotEqual(bakeoff._seed("binding", 1), bakeoff._seed("binding", 2))


if __name__ == "__main__":
    unittest.main()
