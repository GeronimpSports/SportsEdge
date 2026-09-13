from __future__ import annotations

import json
from pathlib import Path
import unittest

from sportsedge.sports.nfl.source_contract import expand_nfl_source_contract
from sportsedge.sports.nfl.source_manifest import (
    NFL_SOURCE_MANIFEST_V2_CONTRACT,
    build_nfl_source_manifest,
    manifest_sha256,
)


CONTRACT_PATH = Path("config/nfl_promotion_source_freeze_v1.json")


class NFLSourceManifestTests(unittest.TestCase):
    def test_manifest_hash_is_canonical_and_order_independent(self):
        left = build_nfl_source_manifest([
            {"name": "schedule", "uri": "u1", "sha256": "a" * 64},
            {"name": "pbp_2024", "uri": "u2", "sha256": "b" * 64},
        ], schedule_anchor_sha256="a" * 64)
        right = build_nfl_source_manifest([
            {"sha256": "b" * 64, "uri": "u2", "name": "pbp_2024"},
            {"sha256": "a" * 64, "name": "schedule", "uri": "u1"},
        ], schedule_anchor_sha256="a" * 64)
        self.assertEqual(manifest_sha256(left), manifest_sha256(right))

    def test_legacy_call_remains_exact_v1_shape(self):
        manifest = build_nfl_source_manifest([
            {"name": "schedule", "uri": "u1", "sha256": "a" * 64},
        ], schedule_anchor_sha256="a" * 64)
        self.assertEqual(manifest, {
            "schema_version": 1,
            "sport": "nfl",
            "schedule_anchor_sha256": "a" * 64,
            "sources": [{"name": "schedule", "uri": "u1", "sha256": "a" * 64}],
        })

    def test_duplicate_source_name_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_NAME_DUPLICATE"):
            build_nfl_source_manifest([
                {"name": "schedule", "uri": "u1", "sha256": "a" * 64},
                {"name": "schedule", "uri": "u2", "sha256": "b" * 64},
            ], schedule_anchor_sha256="a" * 64)

    def test_schedule_anchor_must_match_schedule_entry(self):
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_SCHEDULE_ANCHOR_MISMATCH"):
            build_nfl_source_manifest([
                {"name": "schedule", "uri": "u1", "sha256": "b" * 64},
            ], schedule_anchor_sha256="a" * 64)

    def test_changing_any_source_hash_changes_manifest_hash(self):
        first = build_nfl_source_manifest([
            {"name": "schedule", "uri": "u1", "sha256": "a" * 64},
            {"name": "stadiums", "uri": "u2", "sha256": "b" * 64},
        ], schedule_anchor_sha256="a" * 64)
        second = build_nfl_source_manifest([
            {"name": "schedule", "uri": "u1", "sha256": "a" * 64},
            {"name": "stadiums", "uri": "u2", "sha256": "c" * 64},
        ], schedule_anchor_sha256="a" * 64)
        self.assertNotEqual(manifest_sha256(first), manifest_sha256(second))

    def test_frozen_contract_builds_v2_with_expected_observed_and_upstream_identity(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        expanded = expand_nfl_source_contract(contract)
        observed = [
            {"name": name, "uri": f"observed://{name}", "sha256": row["expected_sha256"]}
            for name, row in reversed(list(expanded.items()))
        ]
        manifest = build_nfl_source_manifest(
            observed,
            schedule_anchor_sha256=expanded["schedule"]["expected_sha256"],
            source_contract=contract,
        )
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["contract"], NFL_SOURCE_MANIFEST_V2_CONTRACT)
        self.assertEqual(manifest["source_count"], 33)
        self.assertEqual(len(manifest["source_contract_sha256"]), 64)
        schedule = next(row for row in manifest["sources"] if row["name"] == "schedule")
        self.assertEqual(schedule["expected_sha256"], schedule["observed_sha256"])
        self.assertEqual(schedule["sha256"], schedule["observed_sha256"])
        self.assertNotEqual(schedule["uri"], "observed://schedule")
        self.assertEqual(schedule["upstream_identity"]["type"], "git_commit_blob")

    def test_v2_rejects_observed_drift_before_manifest_creation(self):
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        expanded = expand_nfl_source_contract(contract)
        observed = [
            {"name": name, "uri": f"observed://{name}", "sha256": row["expected_sha256"]}
            for name, row in expanded.items()
        ]
        next(row for row in observed if row["name"] == "depth_2025")["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_SHA256_MISMATCH:depth_2025"):
            build_nfl_source_manifest(
                observed,
                schedule_anchor_sha256=expanded["schedule"]["expected_sha256"],
                source_contract=contract,
            )


if __name__ == "__main__":
    unittest.main()
