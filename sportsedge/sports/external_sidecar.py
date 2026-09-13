"""Shared, sidecar-only integrity guards for external MLB/CFB/NFL research inputs.

This module is deliberately outside each sport's production model path.  It may help
materialize and audit external source snapshots, but it cannot create Model_P, alter
features/coefficients/RNG policy, satisfy Truth Gate evidence, or change eligibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping


class ExternalSidecarError(ValueError):
    pass


def _utc(value: Any, field: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise ExternalSidecarError(f"{field}:REQUIRED")
    try:
        out = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ExternalSidecarError(f"{field}:INVALID") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise ExternalSidecarError(f"{field}:TIMEZONE_REQUIRED")
    return out.astimezone(timezone.utc)


def build_external_snapshot_manifest(
    *,
    sport: str,
    source_repository: str,
    source_contract: str,
    source_native_id: str,
    source_observed_at_utc: str,
    ingested_at_utc: str,
    target_start_utc: str,
    raw_bytes: bytes,
    raw_path: str,
) -> dict[str, Any]:
    """Create an immutable research-sidecar manifest for one external snapshot.

    A usable pregame candidate must be observed strictly before the target start.
    Ingestion may happen later; keeping the two clocks separate prevents ingestion time
    from being misrepresented as historical availability proof.
    """
    normalized_sport = str(sport or "").strip().upper()
    if normalized_sport not in {"MLB", "CFB", "NFL"}:
        raise ExternalSidecarError("SPORT_UNSUPPORTED")
    repo = str(source_repository or "").strip()
    contract = str(source_contract or "").strip()
    native_id = str(source_native_id or "").strip()
    path = str(raw_path or "").strip()
    if not all((repo, contract, native_id, path)):
        raise ExternalSidecarError("REQUIRED_IDENTITY_FIELD_MISSING")
    observed = _utc(source_observed_at_utc, "source_observed_at_utc")
    ingested = _utc(ingested_at_utc, "ingested_at_utc")
    target = _utc(target_start_utc, "target_start_utc")
    if observed >= target:
        raise ExternalSidecarError("SOURCE_NOT_STRICTLY_PREGAME")
    if ingested < observed:
        raise ExternalSidecarError("INGESTION_PRECEDES_SOURCE_OBSERVATION")
    if not raw_bytes:
        raise ExternalSidecarError("RAW_BYTES_EMPTY")
    return {
        "schema_version": "EXTERNAL_RESEARCH_SNAPSHOT_V1",
        "sport": normalized_sport,
        "source_repository": repo,
        "source_contract": contract,
        "source_native_id": native_id,
        "source_observed_at_utc": observed.isoformat(),
        "ingested_at_utc": ingested.isoformat(),
        "target_start_utc": target.isoformat(),
        "raw_path": path,
        "raw_byte_count": len(raw_bytes),
        "raw_sha256": sha256(raw_bytes).hexdigest(),
        "status": "RESEARCH_SIDECAR_ONLY",
        "predictive_model_input": False,
        "model_p_authority": False,
        "truth_gate_input": False,
        "promotion_authority": False,
        "may_change_market_eligibility": False,
    }


def validate_schedule_identity(
    *,
    canonical_native_id: str,
    observed_native_id: str,
    canonical_start_utc: str,
    observed_start_utc: str,
    max_start_skew_seconds: int = 900,
) -> dict[str, Any]:
    """Fail closed on event-ID or material start-time disagreement."""
    canonical_id = str(canonical_native_id or "").strip()
    observed_id = str(observed_native_id or "").strip()
    if not canonical_id or not observed_id:
        raise ExternalSidecarError("EVENT_ID_REQUIRED")
    if canonical_id != observed_id:
        raise ExternalSidecarError("EVENT_ID_MISMATCH")
    if max_start_skew_seconds < 0:
        raise ExternalSidecarError("MAX_START_SKEW_NEGATIVE")
    canonical_start = _utc(canonical_start_utc, "canonical_start_utc")
    observed_start = _utc(observed_start_utc, "observed_start_utc")
    skew = abs((observed_start - canonical_start).total_seconds())
    if skew > max_start_skew_seconds:
        raise ExternalSidecarError(
            f"EVENT_START_MISMATCH:{int(skew)}>{int(max_start_skew_seconds)}"
        )
    return {
        "status": "IDENTITY_VALIDATED",
        "event_id": canonical_id,
        "start_skew_seconds": skew,
        "model_p_authority": False,
        "promotion_authority": False,
    }


def validate_revision_chain(
    *, previous_manifest: Mapping[str, Any], current_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Treat changed provider bytes as a new immutable revision, never silent overwrite."""
    prev_id = str(previous_manifest.get("source_native_id") or "")
    cur_id = str(current_manifest.get("source_native_id") or "")
    if not prev_id or prev_id != cur_id:
        raise ExternalSidecarError("REVISION_IDENTITY_MISMATCH")
    prev_sha = str(previous_manifest.get("raw_sha256") or "")
    cur_sha = str(current_manifest.get("raw_sha256") or "")
    if not prev_sha or not cur_sha:
        raise ExternalSidecarError("REVISION_SHA_MISSING")
    return {
        "status": "UNCHANGED" if prev_sha == cur_sha else "NEW_IMMUTABLE_REVISION_REQUIRED",
        "source_native_id": cur_id,
        "previous_raw_sha256": prev_sha,
        "current_raw_sha256": cur_sha,
        "silent_overwrite_allowed": False,
        "model_p_authority": False,
        "promotion_authority": False,
    }
