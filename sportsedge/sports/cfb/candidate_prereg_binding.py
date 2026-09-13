"""Cryptographic and semantic binding for the frozen CFB four-candidate preregistration.

This verifier performs no fitting, scoring, or evaluation. READY means only that the
four candidate definitions are frozen, executable, and byte-bound before attempt 1.
"""
from __future__ import annotations

from hashlib import sha1, sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .model_selection_prereg import audit_model_selection_prereg


class CFBCandidatePreregBindingError(ValueError):
    pass


def _read_json_bytes(path: Path) -> tuple[bytes, Mapping[str, Any]]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CFBCandidatePreregBindingError(f"CFB_PREREG_JSON_INVALID:{path}") from exc
    if not isinstance(value, Mapping):
        raise CFBCandidatePreregBindingError(f"CFB_PREREG_JSON_OBJECT_REQUIRED:{path}")
    return raw, value


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return sha1(header + raw).hexdigest()


def verify_candidate_prereg_binding(
    *,
    root: Path,
    policy_path: str = "config/cfb_model_selection_policy_v1.json",
    prereg_path: str = "config/cfb_model_candidate_prereg_v1.json",
    code_manifest_path: str = "config/cfb_model_candidate_code_manifest_v1.json",
    spec_bundle_path: str = "config/cfb_model_candidate_specs_v1.json",
) -> dict[str, Any]:
    root = Path(root)
    _, policy = _read_json_bytes(root / policy_path)
    _, prereg = _read_json_bytes(root / prereg_path)
    code_raw, code_manifest = _read_json_bytes(root / code_manifest_path)
    spec_raw, spec_bundle = _read_json_bytes(root / spec_bundle_path)

    blockers: list[str] = []
    code_sha = sha256(code_raw).hexdigest()
    config_sha = sha256(spec_raw).hexdigest()

    if prereg.get("code_manifest_sha256") != code_sha:
        blockers.append("CODE_MANIFEST_SHA256_MISMATCH")
    if prereg.get("candidate_spec_bundle_sha256") != config_sha:
        blockers.append("SPEC_BUNDLE_SHA256_MISMATCH")

    blob_map = code_manifest.get("git_blob_identities")
    if not isinstance(blob_map, Mapping) or not blob_map:
        blockers.append("CODE_MANIFEST_BLOB_MAP_MISSING")
    else:
        for rel_path, expected in sorted(blob_map.items()):
            path = root / str(rel_path)
            if not path.is_file():
                blockers.append(f"CODE_FILE_MISSING:{rel_path}")
                continue
            actual = _git_blob_sha(path.read_bytes())
            if actual != expected:
                blockers.append(f"CODE_GIT_BLOB_MISMATCH:{rel_path}")

    policy_families = policy.get("candidate_families_predeclared")
    spec_candidates = spec_bundle.get("candidates")
    prereg_candidates = prereg.get("candidates")
    if not isinstance(policy_families, list):
        blockers.append("POLICY_FAMILIES_INVALID")
        policy_families = []
    if not isinstance(spec_candidates, Mapping):
        blockers.append("SPEC_CANDIDATES_INVALID")
        spec_candidates = {}
    if not isinstance(prereg_candidates, Mapping):
        blockers.append("PREREG_CANDIDATES_INVALID")
        prereg_candidates = {}

    common_features = spec_bundle.get("common_feature_list")
    common_training = spec_bundle.get("common_training_window")
    common_hp = spec_bundle.get("common_hyperparameter_policy")
    source_contract = spec_bundle.get("source_contract_identity")
    if not isinstance(common_features, list) or not common_features:
        blockers.append("SPEC_COMMON_FEATURE_LIST_INVALID")
        common_features = []

    for family in policy_families:
        spec = spec_candidates.get(family)
        candidate = prereg_candidates.get(family)
        if not isinstance(spec, Mapping) or not isinstance(candidate, Mapping):
            blockers.append(f"CANDIDATE_BINDING_MISSING:{family}")
            continue
        expected_features = list(common_features) + list(spec.get("extra_feature_list") or [])
        checks = {
            "formula": spec.get("formula"),
            "feature_list": expected_features,
            "weighting_blending_constants": spec.get("weighting_blending_constants"),
            "training_window": common_training,
            "hyperparameter_policy": common_hp,
            "source_contract_identity": source_contract,
            "code_sha256": code_sha,
            "config_sha256": config_sha,
        }
        for field, expected in checks.items():
            if candidate.get(field) != expected:
                blockers.append(f"CANDIDATE_FIELD_MISMATCH:{family}:{field}")

    audit = audit_model_selection_prereg(policy, prereg)
    if audit.get("status") != "READY_FOR_FIRST_EVALUATION":
        blockers.append("PREREG_AUDIT_NOT_READY")

    ready = not blockers
    return {
        "schema": "CFB_MODEL_CANDIDATE_PREREG_BINDING_V1",
        "status": "READY_FOR_FIRST_EVALUATION" if ready else "BLOCKED_PREREG_BINDING",
        "code_manifest_sha256": code_sha,
        "candidate_spec_bundle_sha256": config_sha,
        "candidate_attempt_budget": audit.get("candidate_attempt_budget"),
        "attempts_consumed": audit.get("attempts_consumed"),
        "implemented_families": audit.get("implemented_families"),
        "blockers": blockers,
        "underlying_prereg_audit": audit,
        "evaluation_performed": False,
        "attempt_consumed_by_this_verifier": False,
        "model_p_created": False,
        "promotion_authority": False,
        "eligibility_changed": False,
        "official_authority": False,
    }


__all__ = ["CFBCandidatePreregBindingError", "verify_candidate_prereg_binding"]
