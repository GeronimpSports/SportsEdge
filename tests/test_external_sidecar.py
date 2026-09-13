from __future__ import annotations

import json
from pathlib import Path

import pytest

from sportsedge.sports.external_sidecar import (
    ExternalSidecarError,
    build_external_snapshot_manifest,
    validate_revision_chain,
    validate_schedule_identity,
)


def test_registry_cannot_touch_model_authority() -> None:
    cfg = json.loads(Path("config/all_sports_external_repo_adoptions_v1.json").read_text())
    assert cfg["status"] == "RESEARCH_AND_ENGINEERING_REFERENCE_ONLY"
    assert cfg["governance"]["adoption_mode"] == "SIDE_CAR_ONLY_UNTIL_SEPARATELY_VALIDATED"
    for key, value in cfg["authority"].items():
        assert value is False, key
    assert cfg["governance"]["may_modify_existing_model_coefficients"] is False
    assert cfg["governance"]["may_modify_existing_model_features"] is False
    assert cfg["governance"]["may_replace_existing_rng_contract"] is False


@pytest.mark.parametrize("sport", ["MLB", "CFB", "NFL"])
def test_manifest_is_research_only_for_all_three_sports(sport: str) -> None:
    row = build_external_snapshot_manifest(
        sport=sport,
        source_repository="example/public-repo",
        source_contract="TEST_V1",
        source_native_id="game-1",
        source_observed_at_utc="2026-09-12T15:00:00Z",
        ingested_at_utc="2026-09-12T15:01:00Z",
        target_start_utc="2026-09-12T17:00:00Z",
        raw_bytes=b"raw-provider-payload",
        raw_path="runtime/research/raw.json",
    )
    assert row["sport"] == sport
    assert row["status"] == "RESEARCH_SIDECAR_ONLY"
    assert row["raw_byte_count"] == len(b"raw-provider-payload")
    assert row["model_p_authority"] is False
    assert row["truth_gate_input"] is False
    assert row["promotion_authority"] is False
    assert row["may_change_market_eligibility"] is False


def test_post_start_snapshot_is_rejected() -> None:
    with pytest.raises(ExternalSidecarError, match="SOURCE_NOT_STRICTLY_PREGAME"):
        build_external_snapshot_manifest(
            sport="NFL",
            source_repository="nflverse/nflverse-data",
            source_contract="TEST_V1",
            source_native_id="game-1",
            source_observed_at_utc="2026-09-12T17:00:00Z",
            ingested_at_utc="2026-09-12T17:01:00Z",
            target_start_utc="2026-09-12T17:00:00Z",
            raw_bytes=b"x",
            raw_path="raw.json",
        )


def test_event_id_and_schedule_mismatch_fail_closed() -> None:
    with pytest.raises(ExternalSidecarError, match="EVENT_ID_MISMATCH"):
        validate_schedule_identity(
            canonical_native_id="a",
            observed_native_id="b",
            canonical_start_utc="2026-09-12T17:00:00Z",
            observed_start_utc="2026-09-12T17:00:00Z",
        )
    with pytest.raises(ExternalSidecarError, match="EVENT_START_MISMATCH"):
        validate_schedule_identity(
            canonical_native_id="a",
            observed_native_id="a",
            canonical_start_utc="2026-09-12T17:00:00Z",
            observed_start_utc="2026-09-12T18:00:00Z",
            max_start_skew_seconds=900,
        )


def test_revised_bytes_require_new_immutable_revision() -> None:
    prior = {
        "source_native_id": "game-1",
        "raw_sha256": "a" * 64,
    }
    current = {
        "source_native_id": "game-1",
        "raw_sha256": "b" * 64,
    }
    result = validate_revision_chain(previous_manifest=prior, current_manifest=current)
    assert result["status"] == "NEW_IMMUTABLE_REVISION_REQUIRED"
    assert result["silent_overwrite_allowed"] is False
    assert result["model_p_authority"] is False
