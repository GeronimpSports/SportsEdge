#!/usr/bin/env python3
"""Activate the human-approved NFL V2K V2 reference without mutating frozen V1 governance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

APPROVED_POLICY = "MODERN_REG_2018_2025"
EXPECTED_PROPOSAL_BLOB = "2109c6d7546bbbed2b5c587eb13fd52d9325f488"
EXPECTED_PREREG_BLOB = "f8487883186fc85b77f4e632b1aa710327473b8a"
EXPECTED_V1_REFERENCE_BLOB = "29f351d7ca37346795a8ce8e3cca8b01eda7914e"
EXPECTED_LEDGER_BLOB = "14022680891de3c3d73013ffabc8aee4611e86e6"
HUMAN_APPROVAL_PR = 587
HUMAN_APPROVAL_COMMENT_ID = 5654266444
HUMAN_APPROVAL_BODY_SHA256 = "eaca7bdc5b71f4b08b3ab6a54acda9d292d1f1443d21f3499a5e43b528a95ead"
CANDIDATE_FAMILY = "NFL_V2K_DRIVE_HIERARCHICAL_JOINT_G1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def load_bound(path: Path, expected_blob: str, label: str) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    actual = git_blob_sha(raw)
    if actual != expected_blob:
        raise SystemExit(f"{label}_GIT_BLOB_MISMATCH:{actual}")
    return json.loads(raw), raw


def build(
    proposal_path: Path,
    prereg_path: Path,
    v1_reference_path: Path,
    ledger_path: Path,
) -> tuple[dict, dict]:
    proposal, proposal_raw = load_bound(proposal_path, EXPECTED_PROPOSAL_BLOB, "PROPOSAL")
    prereg_raw = prereg_path.read_bytes()
    if git_blob_sha(prereg_raw) != EXPECTED_PREREG_BLOB:
        raise SystemExit("PREREG_GIT_BLOB_MISMATCH")
    v1_reference, _ = load_bound(v1_reference_path, EXPECTED_V1_REFERENCE_BLOB, "V1_REFERENCE")
    ledger, _ = load_bound(ledger_path, EXPECTED_LEDGER_BLOB, "ATTEMPT_LEDGER")

    if proposal.get("schema") != "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2_PROPOSAL":
        raise SystemExit("PROPOSAL_SCHEMA_MISMATCH")
    if proposal.get("status") != "PROPOSED_HUMAN_REVIEW_REQUIRED":
        raise SystemExit("PROPOSAL_STATUS_MISMATCH")
    if proposal.get("selected_policy") is not None or proposal.get("review_decision") is not None:
        raise SystemExit("REPORT_ONLY_PROPOSAL_MUST_REMAIN_UNSELECTED")
    if proposal.get("implementation_admitted") is not False:
        raise SystemExit("REPORT_ONLY_PROPOSAL_MUST_NOT_ADMIT_IMPLEMENTATION")
    if v1_reference.get("status") != "BLOCKED_REFERENCE_NOT_BUILT":
        raise SystemExit("FROZEN_V1_REFERENCE_WAS_MUTATED")
    if ledger.get("status") != "FROZEN_BEFORE_IMPLEMENTATION":
        raise SystemExit("ATTEMPT_LEDGER_STATUS_MISMATCH")
    if ledger.get("attempts_used") != 0 or ledger.get("max_development_attempts") != 5:
        raise SystemExit("ATTEMPT_BUDGET_MISMATCH")
    if ledger.get("candidate_family") != CANDIDATE_FAMILY:
        raise SystemExit("CANDIDATE_FAMILY_MISMATCH")

    profile = (proposal.get("evidence_profiles") or {}).get(APPROVED_POLICY)
    if not profile:
        raise SystemExit("APPROVED_POLICY_PROFILE_MISSING")
    policy = profile.get("policy") or {}
    if (
        policy.get("first_season") != 2018
        or policy.get("last_season") != 2025
        or policy.get("season_types") != ["REG"]
        or policy.get("sign_convention") != "OFFICIAL_SCHEDULE_HOME_FINAL_MINUS_AWAY_FINAL"
        or policy.get("neutral_site_handling") != "INCLUDE_USING_OFFICIAL_SCHEDULE_HOME_AWAY_DESIGNATION"
        or policy.get("overtime_handling") != "OFFICIAL_FINAL_SCORE_INCLUDING_OVERTIME"
    ):
        raise SystemExit("APPROVED_POLICY_SEMANTICS_MISMATCH")
    if profile.get("game_count") != 2127:
        raise SystemExit("APPROVED_POLICY_GAME_COUNT_MISMATCH")

    tolerance = proposal.get("proposed_absolute_mass_tolerance")
    if tolerance != 0.005:
        raise SystemExit("ABSOLUTE_MASS_TOLERANCE_MISMATCH")
    gate = proposal.get("proposed_structural_improvement_gate") or {}
    required_gate = {
        "candidate_must_strictly_improve_calibration_slope_metric": True,
        "candidate_must_strictly_improve_signed_key_mass_metric": True,
        "absolute_per_key_tolerance_still_required": True,
        "ci_does_not_relax_absolute_mass_tolerance": True,
        "either_dimension_alone_counts_as_pass": False,
    }
    for key, expected in required_gate.items():
        if gate.get(key) is not expected:
            raise SystemExit(f"STRUCTURAL_GATE_MISMATCH:{key}")

    builder_sha256 = sha256_bytes(Path(__file__).read_bytes())
    human_approval = {
        "decision": "SELECT_MODERN_REG_2018_2025",
        "source_pr": HUMAN_APPROVAL_PR,
        "source_comment_id": HUMAN_APPROVAL_COMMENT_ID,
        "source_comment_body_sha256": HUMAN_APPROVAL_BODY_SHA256,
        "recorded_date": "2026-09-13",
        "versioned_activation_only": True,
        "frozen_v1_rewrite_forbidden": True,
    }

    reference = {
        "schema": "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2",
        "status": "FROZEN_READY",
        "authority": "REFERENCE_ONLY",
        "selected_policy": APPROVED_POLICY,
        "purpose": "Frozen empirical signed-key reference for research-only V2K implementation and later untouched validation.",
        "human_approval": human_approval,
        "absolute_mass_tolerance": tolerance,
        "uncertainty_policy": proposal["uncertainty_policy"],
        "policy": policy,
        "game_count": profile["game_count"],
        "per_season_game_count": profile["per_season_game_count"],
        "signed_margin_mass": profile["signed_margin_mass"],
        "frozen_m2_control": profile["control_metrics"],
        "structural_improvement_gate": {
            **gate,
            "status": "FROZEN",
        },
        "source_provenance": {
            **proposal["source_provenance"],
            "report_only_proposal_git_blob_sha1": EXPECTED_PROPOSAL_BLOB,
            "activation_builder_sha256": builder_sha256,
        },
        "freeze_attestation": {
            "derived_from_report_only_proposal": True,
            "approved_policy_hard_coded_from_human_decision": True,
            "sportsbook_prices_used": False,
            "v2k_simulations_used": False,
            "v1_reference_mutated": False,
            "preregistration_mutated": False,
            "attempt_ledger_mutated": False,
            "attempt_consumed_by_activation": False,
            "confidence_intervals_relax_tolerance": False,
        },
    }
    reference_bytes = (json.dumps(reference, indent=2, sort_keys=True) + "\n").encode("utf-8")

    admission = {
        "schema": "NFL_V2K_IMPLEMENTATION_ADMISSION_V2",
        "status": "ADMITTED_RESEARCH_IMPLEMENTATION_ONLY",
        "effective_only_when_merged_to_main": True,
        "candidate_family": CANDIDATE_FAMILY,
        "authority": {
            "research_implementation": True,
            "model_p": False,
            "promotion": False,
            "staking": False,
            "pricing": False,
            "run_it": False,
            "official": False,
            "untouched_readout": False,
        },
        "human_approval": human_approval,
        "attempt_budget": {
            "max_development_attempts": 5,
            "attempts_used": 0,
            "attempt_consumed_by_activation": False,
            "first_materially_different_fitted_specification_evaluated_on_development_validation_consumes_attempt_1": True,
        },
        "bindings": {
            "preregistration_git_blob_sha1": EXPECTED_PREREG_BLOB,
            "frozen_v1_reference_git_blob_sha1": EXPECTED_V1_REFERENCE_BLOB,
            "v1_attempt_ledger_git_blob_sha1": EXPECTED_LEDGER_BLOB,
            "report_only_v2_proposal_git_blob_sha1": EXPECTED_PROPOSAL_BLOB,
            "frozen_v2_reference_sha256": sha256_bytes(reference_bytes),
            "activation_builder_sha256": builder_sha256,
        },
        "admission_conditions": {
            "v2_reference_status_must_be_frozen_ready": True,
            "approved_policy_must_equal": APPROVED_POLICY,
            "market_features_forbidden_in_model_fit": True,
            "uploaded_demo_coefficients_as_fitted_parameters_forbidden": True,
            "untouched_readout_remains_blocked_until_preregistered_folds_sources_features_rng_simulation_count_thresholds_are_frozen": True,
            "bettor_facing_authority_requires_separate_release_bridge": True,
            "release_bridge_issue": 608,
        },
    }
    return reference, admission


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--v1-reference", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--reference-output", required=True)
    parser.add_argument("--admission-output", required=True)
    args = parser.parse_args()

    reference, admission = build(
        Path(args.proposal),
        Path(args.prereg),
        Path(args.v1_reference),
        Path(args.ledger),
    )
    Path(args.reference_output).write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.admission_output).write_text(json.dumps(admission, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "reference_status": reference["status"],
        "selected_policy": reference["selected_policy"],
        "admission_status": admission["status"],
        "attempts_used": admission["attempt_budget"]["attempts_used"],
        "bettor_facing_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
