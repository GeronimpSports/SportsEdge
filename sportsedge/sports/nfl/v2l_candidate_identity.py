"""Immutable identity binding for NFL V2L research artifacts.

Research-only. Grants no Model_P, promotion, staking, or OFFICIAL authority.
"""
from __future__ import annotations
import hashlib
import json
from typing import Mapping

SCHEMA = "SPORTSEDGE_NFL_V2L_CANDIDATE_IDENTITY_V1"


def _sha64(value: object, label: str) -> str:
    out = str(value or "")
    if len(out) != 64 or any(c not in "0123456789abcdefABCDEF" for c in out):
        raise ValueError(f"{label} must be a 64-character SHA256")
    return out.lower()


def build_candidate_identity(*, prereg_sha256: str, code_sha256: str,
                             source_manifest_sha256: str, feature_policy_sha256: str,
                             eval_policy_sha256: str, benchmark_policy_sha256: str,
                             first_readout_policy_sha256: str, fold_definition_sha256: str,
                             environment_lock_sha256: str, rng_policy: Mapping[str, object]) -> dict:
    if not isinstance(rng_policy, Mapping):
        raise ValueError("rng_policy required")
    required_rng = ("bit_generator", "seed_sequence", "seed", "simulation_count", "numpy_version")
    if any(k not in rng_policy for k in required_rng):
        raise ValueError("complete RNG policy required")
    payload = {
        "schema": SCHEMA,
        "status": "BOUND_BEFORE_FIRST_READOUT",
        "prereg_sha256": _sha64(prereg_sha256, "prereg_sha256"),
        "code_sha256": _sha64(code_sha256, "code_sha256"),
        "source_manifest_sha256": _sha64(source_manifest_sha256, "source_manifest_sha256"),
        "feature_policy_sha256": _sha64(feature_policy_sha256, "feature_policy_sha256"),
        "eval_policy_sha256": _sha64(eval_policy_sha256, "eval_policy_sha256"),
        "benchmark_policy_sha256": _sha64(benchmark_policy_sha256, "benchmark_policy_sha256"),
        "first_readout_policy_sha256": _sha64(first_readout_policy_sha256, "first_readout_policy_sha256"),
        "fold_definition_sha256": _sha64(fold_definition_sha256, "fold_definition_sha256"),
        "environment_lock_sha256": _sha64(environment_lock_sha256, "environment_lock_sha256"),
        "rng_policy": dict(rng_policy),
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["candidate_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    return payload


def bind_distribution(distribution: Mapping[str, object], *, candidate_identity_sha256: str,
                      fit_sha256: str, first_readout_policy_sha256: str) -> dict:
    if not isinstance(distribution, Mapping) or "distribution_sha256" not in distribution:
        raise ValueError("hashed distribution required")
    out = {
        "schema": "SPORTSEDGE_NFL_V2L_BOUND_DISTRIBUTION_V1",
        "candidate_identity_sha256": _sha64(candidate_identity_sha256, "candidate_identity_sha256"),
        "fit_sha256": _sha64(fit_sha256, "fit_sha256"),
        "first_readout_policy_sha256": _sha64(first_readout_policy_sha256, "first_readout_policy_sha256"),
        "distribution_sha256": _sha64(distribution["distribution_sha256"], "distribution_sha256"),
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
    raw = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    out["bound_distribution_sha256"] = hashlib.sha256(raw).hexdigest()
    return out
