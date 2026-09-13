from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.run_nfl_v2_candidate_validation import _verified_manifest
from sportsedge.sports.nfl.source_contract import expand_nfl_source_contract
from sportsedge.sports.nfl.source_manifest import build_nfl_source_manifest, manifest_sha256


class NFLSourceManifestV2ConsumerTests(unittest.TestCase):
    def test_candidate_consumer_accepts_legacy_v1_and_frozen_v2(self):
        v1 = build_nfl_source_manifest(
            [{"name": "schedule", "uri": "fixture://schedule", "sha256": "a" * 64}],
            schedule_anchor_sha256="a" * 64,
        )
        v1["manifest_sha256"] = manifest_sha256(v1)
        digest, rows = _verified_manifest(v1)
        self.assertEqual(digest, v1["manifest_sha256"])
        self.assertEqual(rows, {"schedule": "a" * 64})

        contract = json.loads(
            Path("config/nfl_promotion_source_freeze_v1.json").read_text(encoding="utf-8")
        )
        expanded = expand_nfl_source_contract(contract)
        observed = [
            {"name": name, "uri": f"observed://{name}", "sha256": row["expected_sha256"]}
            for name, row in expanded.items()
        ]
        v2 = build_nfl_source_manifest(
            observed,
            schedule_anchor_sha256=expanded["schedule"]["expected_sha256"],
            source_contract=contract,
        )
        v2["manifest_sha256"] = manifest_sha256(v2)
        v2["participation_attribution"] = {"license": "fixture-after-hash"}
        digest, rows = _verified_manifest(v2)
        self.assertEqual(digest, v2["manifest_sha256"])
        self.assertEqual(len(rows), 33)
        self.assertEqual(rows["schedule"], expanded["schedule"]["expected_sha256"])

    def test_candidate_consumer_detects_tampered_v2_identity_metadata(self):
        contract = json.loads(
            Path("config/nfl_promotion_source_freeze_v1.json").read_text(encoding="utf-8")
        )
        expanded = expand_nfl_source_contract(contract)
        observed = [
            {"name": name, "uri": f"observed://{name}", "sha256": row["expected_sha256"]}
            for name, row in expanded.items()
        ]
        v2 = build_nfl_source_manifest(
            observed,
            schedule_anchor_sha256=expanded["schedule"]["expected_sha256"],
            source_contract=contract,
        )
        v2["manifest_sha256"] = manifest_sha256(v2)
        tampered = deepcopy(v2)
        tampered["source_contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(SystemExit, "NFL_M2_V2_SOURCE_MANIFEST_HASH_MISMATCH"):
            _verified_manifest(tampered)


if __name__ == "__main__":
    unittest.main()
