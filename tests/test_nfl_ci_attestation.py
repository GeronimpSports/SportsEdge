import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sportsedge.core.validation.nfl_ci_attestation import verify_nfl_pre_ci_bundle
from sportsedge.sports.nfl.m2 import (
    NFLM2ScoreModel,
    NFL_M2_FEATURE_CONTRACT,
    PRODUCTION_NFL_M2_MODEL_ID,
)
from sportsedge.sports.nfl.model_artifact import build_nfl_m2_model_artifact


class NFLCIAttestationTests(unittest.TestCase):
    def _model_artifact(self, git_sha: str):
        model = NFLM2ScoreModel(
            model_id=PRODUCTION_NFL_M2_MODEL_ID,
            feature_contract=NFL_M2_FEATURE_CONTRACT,
            feature_names=("home_x", "away_x"),
            feature_means=(0.0, 0.0),
            feature_scales=(1.0, 1.0),
            margin_coefficients=(0.0, 1.0, -1.0),
            total_coefficients=(44.0, 0.1, 0.1),
            train_seasons=(2024, 2025),
            ridge_alpha=10.0,
            margin_sigma=13.0,
            total_sigma=10.0,
            residual_correlation=0.0,
            residual_pairs=((1.0, 1.0), (-1.0, -1.0)),
        )
        return build_nfl_m2_model_artifact(
            model,
            code_git_sha=git_sha,
            source_manifest_sha256="a" * 64,
        )

    @staticmethod
    def _artifact_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _refresh_manifest_artifact_hash(self, root: Path, name: str) -> None:
        manifest_path = root / "nfl_promotion_evidence_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in manifest["artifacts"]:
            if row["path"] == name:
                row["sha256"] = self._artifact_hash(root / name)
                break
        else:
            raise AssertionError(f"artifact row missing: {name}")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _write_bundle(
        self,
        root: Path,
        *,
        git_sha: str = "1" * 40,
        evidence_schema: int = 2,
    ) -> None:
        source_manifest_sha = "a" * 64
        source_contract_sha = "b" * 64
        math = {
            "math_artifact": {
                "source_sha256": source_manifest_sha,
                "code_git_sha": git_sha,
            }
        }
        history = {
            "source_sha256": source_manifest_sha,
            "source_manifest_sha256": source_manifest_sha,
            "code_git_sha": git_sha,
            "model_id": PRODUCTION_NFL_M2_MODEL_ID,
            "feature_contract": NFL_M2_FEATURE_CONTRACT,
        }
        registry = {
            "source_sha256": source_manifest_sha,
            "source_manifest_sha256": source_manifest_sha,
            "model_id": PRODUCTION_NFL_M2_MODEL_ID,
            "feature_contract": NFL_M2_FEATURE_CONTRACT,
            "ci_attestation_state": "UNATTESTED_IN_RUNNING_WORKFLOW",
        }
        source = {"manifest_sha256": source_manifest_sha}
        if evidence_schema == 3:
            source.update({
                "schema_version": 2,
                "source_contract_sha256": source_contract_sha,
            })
        payloads = {
            "nfl_simulator_profile.json": math,
            "nfl_production_validation.json": history,
            "nfl_promotion_registry.json": registry,
            "nfl_source_manifest.json": source,
            "nfl_m2_model.json": self._model_artifact(git_sha),
        }
        if evidence_schema == 3:
            payloads["nfl_source_freeze_attestation.json"] = {
                "status": "PASS",
                "phase": "PRE_MODEL_FIT",
                "verified_before_model_fit": True,
                "bundle_upgrade_status": "PASS",
                "source_contract_sha256": source_contract_sha,
                "v2_source_manifest_sha256": source_manifest_sha,
            }

        hashes = {}
        for name, payload in payloads.items():
            path = root / name
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            hashes[name] = self._artifact_hash(path)

        manifest = {
            "schema_version": evidence_schema,
            "git_sha": git_sha,
            "source_manifest_sha256": source_manifest_sha,
            "ci_attestation_state": "PRE_CI_WORKFLOW_CANNOT_SELF_ATTEST",
            "artifacts": [
                {"path": name, "sha256": digest}
                for name, digest in sorted(hashes.items())
            ],
        }
        if evidence_schema == 3:
            manifest.update({
                "source_contract_sha256": source_contract_sha,
                "source_freeze_attestation_status": "PASS",
            })
        (root / "nfl_promotion_evidence_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _verify(
        self,
        root: Path,
        *,
        sha: str = "1" * 40,
        conclusion: str = "success",
        name: str = "football-nfl-promotion-evidence",
    ):
        return verify_nfl_pre_ci_bundle(
            root,
            workflow_name=name,
            workflow_conclusion=conclusion,
            workflow_head_sha=sha,
            workflow_run_id=12345,
        )

    def test_exact_successful_v2_head_attests_model_and_bundle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root)
            result = self._verify(root)
            self.assertEqual(result["git_sha"], "1" * 40)
            self.assertEqual(result["trained_through_season"], 2025)
            self.assertEqual(result["verified_artifact_count"], 5)
            self.assertFalse(result["source_freeze_attested"])
            self.assertEqual(result["evidence_manifest_schema_version"], 2)
            self.assertIsNone(result["source_contract_sha256"])
            self.assertRegex(result["model_artifact_sha256"], r"^[0-9a-f]{64}$")

    def test_exact_successful_v3_requires_and_attests_frozen_sources(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root, evidence_schema=3)
            result = self._verify(root)
            self.assertEqual(result["evidence_manifest_schema_version"], 3)
            self.assertTrue(result["source_freeze_attested"])
            self.assertEqual(result["source_contract_sha256"], "b" * 64)
            self.assertEqual(result["verified_artifact_count"], 6)

    def test_v3_missing_freeze_artifact_cannot_attest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root, evidence_schema=3)
            manifest_path = root / "nfl_promotion_evidence_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"] = [
                row
                for row in manifest["artifacts"]
                if row["path"] != "nfl_source_freeze_attestation.json"
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (root / "nfl_source_freeze_attestation.json").unlink()
            with self.assertRaisesRegex(
                ValueError,
                "NFL_CI_REQUIRED_ARTIFACT_MISSING:nfl_source_freeze_attestation.json",
            ):
                self._verify(root)

    def test_v3_freeze_contract_tamper_fails_after_outer_hash_is_refreshed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root, evidence_schema=3)
            freeze_path = root / "nfl_source_freeze_attestation.json"
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            freeze["source_contract_sha256"] = "c" * 64
            freeze_path.write_text(json.dumps(freeze, sort_keys=True), encoding="utf-8")
            self._refresh_manifest_artifact_hash(
                root, "nfl_source_freeze_attestation.json"
            )
            with self.assertRaisesRegex(
                ValueError, "NFL_CI_SOURCE_CONTRACT_IDENTITY_MISMATCH"
            ):
                self._verify(root)

    def test_v3_freeze_manifest_binding_tamper_fails_after_outer_hash_is_refreshed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root, evidence_schema=3)
            freeze_path = root / "nfl_source_freeze_attestation.json"
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            freeze["v2_source_manifest_sha256"] = "c" * 64
            freeze_path.write_text(json.dumps(freeze, sort_keys=True), encoding="utf-8")
            self._refresh_manifest_artifact_hash(
                root, "nfl_source_freeze_attestation.json"
            )
            with self.assertRaisesRegex(
                ValueError, "NFL_CI_SOURCE_FREEZE_MANIFEST_BINDING_MISMATCH"
            ):
                self._verify(root)

    def test_v3_source_manifest_contract_tamper_fails_after_outer_hash_is_refreshed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root, evidence_schema=3)
            source_path = root / "nfl_source_manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["source_contract_sha256"] = "c" * 64
            source_path.write_text(json.dumps(source, sort_keys=True), encoding="utf-8")
            self._refresh_manifest_artifact_hash(root, "nfl_source_manifest.json")
            with self.assertRaisesRegex(
                ValueError, "NFL_CI_SOURCE_CONTRACT_IDENTITY_MISMATCH"
            ):
                self._verify(root)

    def test_failed_or_wrong_workflow_cannot_attest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root)
            with self.assertRaisesRegex(ValueError, "NFL_CI_WORKFLOW_NOT_SUCCESSFUL"):
                self._verify(root, conclusion="failure")
            with self.assertRaisesRegex(ValueError, "NFL_CI_WORKFLOW_NAME_MISMATCH"):
                self._verify(root, name="other")

    def test_wrong_head_cannot_attest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root)
            with self.assertRaisesRegex(ValueError, "NFL_CI_HEAD_SHA_MISMATCH"):
                self._verify(root, sha="2" * 40)

    def test_tampered_artifact_fails_hash_verification(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root)
            (root / "nfl_production_validation.json").write_text(
                "{}", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "NFL_CI_ARTIFACT_HASH_MISMATCH"):
                self._verify(root)

    def test_model_artifact_must_be_present_and_exact_identity(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_bundle(root)
            manifest_path = root / "nfl_promotion_evidence_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"] = [
                row
                for row in manifest["artifacts"]
                if row["path"] != "nfl_m2_model.json"
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "NFL_CI_REQUIRED_ARTIFACT_MISSING:nfl_m2_model.json"
            ):
                self._verify(root)


if __name__ == "__main__":
    unittest.main()
