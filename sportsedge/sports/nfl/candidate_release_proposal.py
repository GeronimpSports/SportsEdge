"""Report-only identity contract for a future NFL candidate production release.

A validated research candidate must never become production merely by changing a
model-id string or by inheriting the legacy M2 registry.  This module can create
only a proposal that binds immutable candidate/evidence identities for later human
review.  It cannot admit implementation, freeze an artifact, transfer legacy M2
evidence, authorize Model_P, stake, promote, or create an OFFICIAL play.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from .m2 import PRODUCTION_NFL_M2_MODEL_ID

SCHEMA_VERSION = "NFL_CANDIDATE_RELEASE_PROPOSAL_V1"
PROPOSAL_STATUS = "PROPOSED_HUMAN_REVIEW_REQUIRED"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NFLCandidateReleaseProposalError(ValueError):
    pass


def _text(value: Any, error: str) -> str:
    out = str(value or "").strip()
    if not out:
        raise NFLCandidateReleaseProposalError(error)
    return out


def _git_sha(value: Any, error: str) -> str:
    out = str(value or "").strip().lower()
    if not _GIT_SHA.fullmatch(out):
        raise NFLCandidateReleaseProposalError(error)
    return out


def _sha256(value: Any, error: str) -> str:
    out = str(value or "").strip().lower()
    if not _SHA256.fullmatch(out):
        raise NFLCandidateReleaseProposalError(error)
    return out


def build_candidate_release_proposal(
    *,
    candidate_model_id: str,
    distribution_contract: str,
    preregistration_sha256: str,
    first_readout_sha256: str,
    source_manifest_sha256: str,
    code_git_sha: str,
    readout: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one zero-authority candidate readout into a non-activating proposal."""
    if not isinstance(readout, Mapping):
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_READOUT_REQUIRED")

    model_id = _text(candidate_model_id, "NFL_CANDIDATE_RELEASE_MODEL_ID_REQUIRED")
    if model_id == PRODUCTION_NFL_M2_MODEL_ID:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_LEGACY_M2_RELABEL_PROHIBITED")
    distribution = _text(
        distribution_contract,
        "NFL_CANDIDATE_RELEASE_DISTRIBUTION_CONTRACT_REQUIRED",
    )
    prereg_hash = _sha256(
        preregistration_sha256,
        "NFL_CANDIDATE_RELEASE_PREREG_SHA256_INVALID",
    )
    readout_hash = _sha256(
        first_readout_sha256,
        "NFL_CANDIDATE_RELEASE_READOUT_SHA256_INVALID",
    )
    source_hash = _sha256(
        source_manifest_sha256,
        "NFL_CANDIDATE_RELEASE_SOURCE_SHA256_INVALID",
    )
    code_sha = _git_sha(code_git_sha, "NFL_CANDIDATE_RELEASE_CODE_SHA_INVALID")

    if readout.get("model_id") != model_id:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_READOUT_MODEL_ID_MISMATCH")
    if readout.get("distribution_contract") != distribution:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_READOUT_DISTRIBUTION_MISMATCH")
    if str(readout.get("source_manifest_sha256") or "").strip().lower() != source_hash:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_READOUT_SOURCE_MISMATCH")
    if readout.get("preregistration_locked") is not True:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_PREREG_LOCK_REQUIRED")
    if readout.get("post_readout_retuning_allowed") is not False:
        raise NFLCandidateReleaseProposalError("NFL_CANDIDATE_RELEASE_POST_READOUT_RETUNING_PROHIBITED")

    zero_authority = (
        "promotion_eligible",
        "promotion_authority",
        "model_p_authority",
        "official_status_granted",
        "production_registry_consumes_this_artifact",
    )
    for field in zero_authority:
        if readout.get(field) is not False:
            raise NFLCandidateReleaseProposalError(
                f"NFL_CANDIDATE_RELEASE_ZERO_AUTHORITY_REQUIRED:{field}"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "sport": "nfl",
        "status": PROPOSAL_STATUS,
        "candidate_identity": {
            "model_id": model_id,
            "distribution_contract": distribution,
            "code_git_sha": code_sha,
        },
        "evidence_identity": {
            "preregistration_sha256": prereg_hash,
            "first_readout_sha256": readout_hash,
            "source_manifest_sha256": source_hash,
        },
        "human_review": {
            "review_decision": None,
            "selected_production_release_id": None,
            "implementation_admitted": False,
        },
        "authority": {
            "legacy_m2_evidence_transfer_allowed": False,
            "model_p_authority": False,
            "promotion_authority": False,
            "staking_authority": False,
            "official_authority": False,
            "freeze_authority": False,
            "forward_clv_may_start": False,
        },
        "required_next_steps": [
            "HUMAN_REVIEW_CANDIDATE_VERDICT_AND_IDENTITY",
            "VERSIONED_PRODUCTION_RELEASE_IDENTITY",
            "DETERMINISTIC_CANDIDATE_ARTIFACT_SERIALIZER_AND_LOADER",
            "SAME_RELEASE_HISTORICAL_CALIBRATION_AND_KEY_ATTESTATION",
            "SAME_RELEASE_EXACT_HEAD_CI_ATTESTATION",
            "POST_FREEZE_PROSPECTIVE_FORWARD_CLV",
            "FORMAL_PROMOTION_AND_FROZEN_EDGE_FLOOR_RESOLUTION",
        ],
    }
