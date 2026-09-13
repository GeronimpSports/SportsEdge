from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_nfl_production_validation_frozen import (
    _child_argv,
    _observed_sources,
    upgrade_generated_bundle,
)
from sportsedge.sports.nfl.source_manifest import build_nfl_source_manifest, manifest_sha256


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tiny_contract(hashes: dict[str, str]) -> dict:
    return {
        "schema_version": 1,
        "sport": "nfl",
        "contract": "NFL_PROMOTION_SOURCE_FREEZE_V1",
        "frozen_from_evidence": {
            "sportsedge_code_git_sha": "a" * 40,
            "source_manifest_sha256": "b" * 64,
        },
        "sources": {
            "schedule": {
                "uri": "https://example.test/schedule.csv",
                "expected_sha256": hashes["schedule"],
                "upstream_identity": {
                    "type": "git_commit_blob",
                    "repository": "example/schedule",
                    "commit_sha": "c" * 40,
                    "path": "schedule.csv",
                    "git_blob_sha1": "d" * 40,
                },
            },
            "stadiums": {
                "uri": "https://example.test/stadiums.csv",
                "expected_sha256": hashes["stadiums"],
                "upstream_identity": {
                    "type": "git_commit_path",
                    "repository": "example/stadiums",
                    "commit_sha": "e" * 40,
                    "path": "stadiums.csv",
                },
            },
            "starter_overrides": {
                "uri": "repo://config/overrides.json",
                "expected_sha256": hashes["starter_overrides"],
                "upstream_identity": {
                    "type": "sportsedge_repo_file",
                    "path": "config/overrides.json",
                },
            },
        },
        "seasonal_sources": {
            prefix: {
                "seasons": [2016],
                "uri_template": f"https://example.test/{prefix}_{{season}}.csv",
                "upstream_identity": {
                    "type": "github_release_asset",
                    "repository": "example/data",
                    "release_tag": prefix,
                    "asset_template": f"{prefix}_{{season}}.csv",
                    "provider_release_immutable": False,
                },
                "expected_sha256_by_season": {"2016": hashes[f"{prefix}_2016"]},
            }
            for prefix in ("pbp", "participation", "depth")
        },
    }


def _args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        schedule_file=root / "schedule.csv",
        pbp_dir=root / "pbp",
        participation_dir=root / "participation",
        depth_dir=root / "depth",
        stadium_file=root / "stadiums.csv",
        starter_override_file=root / "overrides.json",
        start_season=2016,
        end_season=2016,
        out=root / "nfl_production_validation.json",
        manifest_out=root / "nfl_source_manifest.json",
        model_out=root / "nfl_m2_model.json",
        qb_coverage_out=root / "nfl_starting_qb_coverage.json",
        source_contract=root / "contract.json",
        freeze_attestation_out=root / "freeze.json",
    )


def _write_source_fixture(root: Path) -> argparse.Namespace:
    args = _args(root)
    args.pbp_dir.mkdir()
    args.participation_dir.mkdir()
    args.depth_dir.mkdir()
    files = {
        args.schedule_file: "schedule",
        args.stadium_file: "stadiums",
        args.starter_override_file: "overrides",
        args.pbp_dir / "play_by_play_2016.csv": "pbp",
        args.participation_dir / "pbp_participation_2016.csv": "participation",
        args.depth_dir / "depth_charts_2016.csv": "depth",
    }
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
    return args


class NFLSourceFreezeWrapperTests(unittest.TestCase):
    def test_wrapper_only_strips_its_private_options_from_child_argv(self):
        raw = [
            "--schedule-file", "s.csv",
            "--source-contract", "freeze.json",
            "--git-sha", "a" * 40,
            "--freeze-attestation-out=att.json",
            "--out", "out.json",
        ]
        self.assertEqual(
            _child_argv(raw),
            ["--schedule-file", "s.csv", "--git-sha", "a" * 40, "--out", "out.json"],
        )

    def test_prefit_inventory_hashes_exact_source_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = _write_source_fixture(root)
            observed = {row["name"]: row for row in _observed_sources(args)}
            self.assertEqual(
                set(observed),
                {"schedule", "stadiums", "starter_overrides", "pbp_2016", "participation_2016", "depth_2016"},
            )
            self.assertEqual(observed["schedule"]["sha256"], _hash("schedule"))
            self.assertEqual(observed["depth_2016"]["sha256"], _hash("depth"))

    def test_duplicate_csv_and_gzip_for_same_season_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = _write_source_fixture(root)
            (args.pbp_dir / "play_by_play_2016.csv.gz").write_bytes(b"duplicate")
            with self.assertRaisesRegex(ValueError, "NFL_FROZEN_SOURCE_FILE_COUNT:2016:play_by_play:2"):
                _observed_sources(args)

    def _legacy_bundle(self, root: Path):
        args = _write_source_fixture(root)
        observed = _observed_sources(args)
        hashes = {row["name"]: row["sha256"] for row in observed}
        contract = _tiny_contract(hashes)
        args.source_contract.write_text(json.dumps(contract), encoding="utf-8")
        legacy = build_nfl_source_manifest(
            [{"name": row["name"], "uri": f"frozen://{row['name']}", "sha256": row["sha256"]} for row in observed],
            schedule_anchor_sha256=hashes["schedule"],
        )
        old_hash = manifest_sha256(legacy)
        legacy_payload = dict(legacy)
        legacy_payload["manifest_sha256"] = old_hash
        legacy_payload["participation_attribution"] = {"license": "fixture"}
        args.manifest_out.write_text(json.dumps(legacy_payload), encoding="utf-8")
        args.out.write_text(json.dumps({
            "source_manifest_sha256": old_hash,
            "source_sha256": old_hash,
            "source_uri": f"manifest://sha256/{old_hash}",
            "promotion_evidence": {"spread": {"source_sha256": old_hash}},
        }), encoding="utf-8")
        args.model_out.write_text(json.dumps({"source_manifest_sha256": old_hash, "model": {"x": 1}}), encoding="utf-8")
        args.qb_coverage_out.write_text(json.dumps({"source_manifest_sha256": old_hash, "status": "PASS"}), encoding="utf-8")
        return args, observed, contract, old_hash

    def test_upgrade_rebinds_generated_bundle_to_v2_without_changing_model_payload(self):
        with tempfile.TemporaryDirectory() as td:
            args, observed, contract, old_hash = self._legacy_bundle(Path(td))
            new_hash = upgrade_generated_bundle(
                args=args, source_contract=contract, observed_sources=observed
            )
            manifest = json.loads(args.manifest_out.read_text(encoding="utf-8"))
            model = json.loads(args.model_out.read_text(encoding="utf-8"))
            evidence = json.loads(args.out.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["manifest_sha256"], new_hash)
            self.assertEqual(manifest["participation_attribution"], {"license": "fixture"})
            self.assertEqual(model["source_manifest_sha256"], new_hash)
            self.assertEqual(model["model"], {"x": 1})
            self.assertEqual(evidence["source_uri"], f"manifest://sha256/{new_hash}")
            self.assertNotIn(old_hash, args.out.read_text(encoding="utf-8"))

    def test_tampered_legacy_manifest_hash_cannot_be_upgraded(self):
        with tempfile.TemporaryDirectory() as td:
            args, observed, contract, _old_hash = self._legacy_bundle(Path(td))
            payload = json.loads(args.manifest_out.read_text(encoding="utf-8"))
            payload["sources"][0]["uri"] = "tampered://source"
            args.manifest_out.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NFL_SOURCE_FREEZE_LEGACY_MANIFEST_HASH_MISMATCH"):
                upgrade_generated_bundle(args=args, source_contract=contract, observed_sources=observed)

    def test_generated_artifact_must_already_bind_legacy_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            args, observed, contract, _old_hash = self._legacy_bundle(Path(td))
            args.model_out.write_text(json.dumps({"model": {"x": 1}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NFL_SOURCE_FREEZE_GENERATED_ARTIFACT_SOURCE_BINDING_MISSING"):
                upgrade_generated_bundle(args=args, source_contract=contract, observed_sources=observed)

    def test_runner_source_set_must_match_contract_before_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            args, observed, contract, _old_hash = self._legacy_bundle(Path(td))
            payload = json.loads(args.manifest_out.read_text(encoding="utf-8"))
            # Recompute a self-consistent V1 hash after deleting a source. The
            # contract, rather than the legacy hash check, must catch the gap.
            payload["sources"] = [row for row in payload["sources"] if row["name"] != "depth_2016"]
            base = dict(payload)
            base.pop("manifest_sha256", None)
            base.pop("participation_attribution", None)
            payload["manifest_sha256"] = manifest_sha256(base)
            args.manifest_out.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "NFL_SOURCE_CONTRACT_REQUIRED_SOURCE_MISSING:depth_2016"):
                upgrade_generated_bundle(args=args, source_contract=contract, observed_sources=observed)


if __name__ == "__main__":
    unittest.main()
