from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/research/nfl_v2j_timeout_successor_v1.json"
WORKFLOW = ROOT / ".github/workflows/nfl-v2j-timeout-successor.yml"
FOLD_SCRIPT = ROOT / "scripts/run_nfl_v2j_fold_shard.py"
MERGE_SCRIPT = ROOT / "scripts/merge_nfl_v2j_fold_shards.py"


class NFLV2JTimeoutSuccessorContractTests(unittest.TestCase):
    def test_policy_frozen_activation_state_is_self_consistent(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["policy_id"], "NFL_V2J_TIMEOUT_SUCCESSOR_V1")
        self.assertIn(
            (policy["status"], policy["execution_enabled"]),
            {
                ("FROZEN_PRE_ACTIVATION", False),
                ("FROZEN_ACTIVE_ONE_SHOT", True),
            },
        )
        self.assertEqual(policy["predecessor"]["workflow_run_id"], 34754505720)
        self.assertEqual(policy["predecessor"]["conclusion"], "cancelled")
        self.assertEqual(policy["predecessor"]["artifacts_emitted"], 0)
        self.assertEqual(
            policy["predecessor"]["interpretation"],
            "INCONCLUSIVE_RUNTIME_TIMEOUT_NO_PREDICTIVE_VERDICT",
        )

    def test_fold_geometry_is_frozen_and_each_projected_fold_fits_ceiling(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        geom = policy["successor_geometry"]
        self.assertEqual(
            geom["strategy"],
            "ONE_JOB_PER_FROZEN_WALK_FORWARD_TEST_SEASON",
        )
        self.assertEqual(geom["test_seasons"], [2020, 2021, 2022, 2023, 2024, 2025])
        self.assertIs(geom["row_subsharding"], False)
        self.assertLess(geom["max_projected_fold_minutes"], geom["hosted_timeout_minutes"])
        measured = policy["exact_runtime_repair_evidence"]["fold_projected_minutes"]
        self.assertEqual(set(measured), {"2020", "2021", "2022", "2023", "2024", "2025"})
        for minutes in measured.values():
            self.assertLess(float(minutes), float(geom["hosted_timeout_minutes"]))

    def test_policy_grants_no_authority(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        authority = policy["authority"]
        self.assertIsNone(authority["predictive_verdict_before_complete_merge"])
        for field in (
            "model_p_authority",
            "promotion_authority",
            "staking_authority",
            "official_authority",
        ):
            self.assertIs(authority[field], False)
        self.assertIs(policy["math_contract"]["post_readout_retuning_allowed"], False)

    def test_main_push_trigger_is_activation_file_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        push_block = text.split("  push:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("branches: [main]", push_block)
        self.assertIn("config/research/nfl_v2j_timeout_successor_v1.json", push_block)
        self.assertNotIn("m2_v2j_runtime_cache.py", push_block)
        self.assertNotIn("m2_v2j_runtime_shard.py", push_block)
        self.assertNotIn("run_nfl_v2j_fold_shard.py", push_block)
        self.assertNotIn("merge_nfl_v2j_fold_shards.py", push_block)

    def test_execution_requires_main_push_and_enabled_policy(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        gate = "github.event_name == 'push' && needs.contract.outputs.execution_enabled == 'true'"
        self.assertGreaterEqual(text.count(gate), 2)
        self.assertIn("test_season: [2020, 2021, 2022, 2023, 2024, 2025]", text)
        self.assertIn("timeout-minutes: 330", text)
        self.assertIn(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
            text,
        )
        self.assertIn("config/nfl_promotion_source_freeze_v1.json", text)

    def test_fold_and_merge_scripts_keep_exact_shard_boundary(self):
        fold = FOLD_SCRIPT.read_text(encoding="utf-8")
        merge = MERGE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("build_v2j_raw_evaluation_shard", fold)
        self.assertIn("shard_index=0", fold)
        self.assertIn("shard_count=1", fold)
        self.assertNotIn("_market_readout(", fold)
        self.assertIn("merge_v2j_raw_evaluation_shards", merge)
        self.assertIn("build_v2j_candidate_evidence_from_raw_exact", merge)
        self.assertIn("_EXPECTED_TEST_SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)", merge)


if __name__ == "__main__":
    unittest.main()
