from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from sportsedge.sports.nfl.source_contract import (
    SOURCE_CONTRACT_ID,
    bind_observed_sources_to_contract,
    expand_nfl_source_contract,
    load_nfl_source_contract,
    source_contract_sha256,
)

CONTRACT_PATH = Path("config/nfl_promotion_source_freeze_v1.json")
SCHEDULE_COMMIT = "33488cbcb33839efeb3776bf81673787d18a2bcf"
SCHEDULE_SHA256 = "45a0a605c4d6a94d241dfc0e4f8d69175001b52ec87d9e4c7ea72902810e9181"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _observed(contract: dict | None = None) -> list[dict[str, str]]:
    resolved = expand_nfl_source_contract(_contract() if contract is None else contract)
    return [
        {"name": name, "sha256": row["expected_sha256"], "uri": "ignored-observed-uri"}
        for name, row in sorted(resolved.items())
    ]


class NFLSourceContractTests(unittest.TestCase):
    def test_checked_in_contract_is_complete_and_schedule_is_commit_pinned(self):
        contract = load_nfl_source_contract(CONTRACT_PATH)
        expanded = expand_nfl_source_contract(contract)
        self.assertEqual(contract["contract"], SOURCE_CONTRACT_ID)
        self.assertEqual(len(expanded), 33)
        schedule = expanded["schedule"]
        self.assertIn(SCHEDULE_COMMIT, schedule["uri"])
        self.assertNotIn("/master/", schedule["uri"])
        self.assertEqual(schedule["expected_sha256"], SCHEDULE_SHA256)
        self.assertEqual(schedule["upstream_identity"]["commit_sha"], SCHEDULE_COMMIT)
        self.assertEqual(
            schedule["upstream_identity"]["git_blob_sha1"],
            "54342c359b42573277a67dcda801519edcb0b1e8",
        )

    def test_release_assets_are_explicitly_treated_as_mutable_and_hash_frozen(self):
        expanded = expand_nfl_source_contract(_contract())
        for name, row in expanded.items():
            if not name.startswith(("pbp_", "participation_", "depth_")):
                continue
            identity = row["upstream_identity"]
            self.assertEqual(identity["type"], "github_release_asset")
            self.assertIs(identity["provider_release_immutable"], False)
            self.assertEqual(len(row["expected_sha256"]), 64)
            self.assertIn(identity["asset_name"], row["uri"])

    def test_contract_hash_is_canonical_across_mapping_order(self):
        contract = _contract()
        reordered = dict(reversed(list(contract.items())))
        self.assertEqual(source_contract_sha256(contract), source_contract_sha256(reordered))

    def test_exact_observed_source_set_binds_to_contract_identity(self):
        contract = _contract()
        attestation = bind_observed_sources_to_contract(_observed(contract), contract)
        self.assertEqual(attestation["status"], "PASS")
        self.assertEqual(attestation["source_count"], 33)
        self.assertEqual(attestation["source_contract_sha256"], source_contract_sha256(contract))
        schedule = next(row for row in attestation["sources"] if row["name"] == "schedule")
        self.assertEqual(schedule["expected_sha256"], SCHEDULE_SHA256)
        self.assertEqual(schedule["observed_sha256"], SCHEDULE_SHA256)
        self.assertIn(SCHEDULE_COMMIT, schedule["uri"])

    def test_observed_hash_drift_fails_closed(self):
        observed = _observed()
        schedule = next(row for row in observed if row["name"] == "schedule")
        schedule["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_SHA256_MISMATCH:schedule"):
            bind_observed_sources_to_contract(observed, _contract())

    def test_missing_extra_and_duplicate_observed_sources_fail_closed(self):
        observed = _observed()
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_REQUIRED_SOURCE_MISSING:schedule"):
            bind_observed_sources_to_contract(
                [row for row in observed if row["name"] != "schedule"], _contract()
            )

        extra = observed + [{"name": "future_source", "sha256": "f" * 64}]
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_UNEXPECTED_SOURCE:future_source"):
            bind_observed_sources_to_contract(extra, _contract())

        duplicate = observed + [deepcopy(observed[0])]
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_OBSERVED_NAME_DUPLICATE"):
            bind_observed_sources_to_contract(duplicate, _contract())

    def test_static_and_seasonal_source_sets_are_closed(self):
        contract = _contract()
        contract["sources"]["mystery"] = deepcopy(contract["sources"]["schedule"])
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_STATIC_SOURCE_SET_INVALID"):
            expand_nfl_source_contract(contract)

        contract = _contract()
        del contract["seasonal_sources"]["depth"]
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_SEASONAL_SOURCE_SET_INVALID"):
            expand_nfl_source_contract(contract)

    def test_season_hash_membership_and_order_cannot_drift(self):
        contract = _contract()
        contract["seasonal_sources"]["pbp"]["seasons"] = [2017, 2016, *range(2018, 2026)]
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_SEASONS_NOT_UNIQUE_SORTED:pbp"):
            expand_nfl_source_contract(contract)

        contract = _contract()
        del contract["seasonal_sources"]["pbp"]["expected_sha256_by_season"]["2016"]
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_HASH_SEASON_SET_INVALID:pbp"):
            expand_nfl_source_contract(contract)

    def test_release_immutability_flag_must_be_literal_boolean(self):
        contract = _contract()
        contract["seasonal_sources"]["pbp"]["upstream_identity"]["provider_release_immutable"] = "false"
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_RELEASE_IMMUTABLE_FLAG_INVALID:pbp_2016"):
            expand_nfl_source_contract(contract)

    def test_evidence_anchor_and_source_hashes_are_strict_hex(self):
        contract = _contract()
        contract["frozen_from_evidence"]["sportsedge_code_git_sha"] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_EVIDENCE_CODE_SHA_INVALID"):
            expand_nfl_source_contract(contract)

        contract = _contract()
        contract["sources"]["schedule"]["expected_sha256"] = "x" * 64
        with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_SHA256_INVALID:schedule"):
            expand_nfl_source_contract(contract)


if __name__ == "__main__":
    unittest.main()
