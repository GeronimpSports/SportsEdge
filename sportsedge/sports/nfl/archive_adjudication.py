"""Fail-closed adjudication for model-free NFL price archive rows.

This module never upgrades archive rows to promotion evidence. Actual-start
metadata may only confirm a scheduled-pregame observation or invalidate it.
Unknown actual start remains unverified and therefore unusable as promotion
or decision evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

UTC = timezone.utc


class ArchiveAdjudicationError(ValueError):
    pass


def _ts(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ArchiveAdjudicationError(f"{field}_MISSING")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ArchiveAdjudicationError(f"{field}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ArchiveAdjudicationError(f"{field}_NAIVE")
    return parsed.astimezone(UTC)


def adjudicate_nfl_archive_row(
    row: Mapping[str, Any],
    *,
    actual_start_time: str | None,
    actual_start_source: str | None,
    actual_start_retrieved_at: str | None,
) -> dict[str, Any]:
    """Return immutable-row adjudication metadata.

    The original row is not mutated. A known actual start can only confirm that
    capture preceded actual start or invalidate it. Missing actual start fails
    closed. Neither result creates Model_P, a decision, OFFICIAL status, or
    promotion authority.
    """
    if row.get("evidence_class") != "NOT_EVIDENCE":
        raise ArchiveAdjudicationError("ARCHIVE_ROW_NOT_NOT_EVIDENCE")
    if str(row.get("sport_key") or "") != "americanfootball_nfl":
        raise ArchiveAdjudicationError("NFL_ARCHIVE_ROW_REQUIRED")

    captured = _ts(row.get("captured_at"), "CAPTURED_AT")
    scheduled = _ts(row.get("commence_time"), "SCHEDULED_COMMENCE_TIME")
    if captured >= scheduled:
        scheduled_status = "INVALID_CAPTURE_AT_OR_AFTER_SCHEDULED_START"
    else:
        scheduled_status = "SCHEDULED_PREGAME"

    base = {
        "schema": "SPORTSEDGE_NFL_ARCHIVE_ACTUAL_START_ADJUDICATION_V1",
        "event_id": str(row.get("event_id") or ""),
        "captured_at": captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scheduled_commence_time": scheduled.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scheduled_status": scheduled_status,
        "source_row_evidence_class": "NOT_EVIDENCE",
        "creates_model_p": False,
        "creates_decision_row": False,
        "promotion_authority": False,
        "official_authority": False,
        "staking_authority": False,
        "can_rescue_missed_or_out_of_window_capture": False,
    }

    if actual_start_time is None:
        return {
            **base,
            "actual_start_status": "UNVERIFIED",
            "actual_start_time": None,
            "actual_start_source": None,
            "actual_start_retrieved_at": None,
            "pregame_actual_start_verified": False,
            "adjudication": "INCONCLUSIVE_ACTUAL_START_UNVERIFIED",
            "eligible_for_promotion_evidence": False,
        }

    actual = _ts(actual_start_time, "ACTUAL_START_TIME")
    source = str(actual_start_source or "").strip()
    if not source:
        raise ArchiveAdjudicationError("ACTUAL_START_SOURCE_REQUIRED")
    retrieved = _ts(actual_start_retrieved_at, "ACTUAL_START_RETRIEVED_AT")

    if captured >= actual:
        verdict = "INVALID_CAPTURE_AT_OR_AFTER_ACTUAL_START"
        verified = False
    elif scheduled_status != "SCHEDULED_PREGAME":
        verdict = "INVALID_SCHEDULED_WINDOW_CANNOT_BE_RESCUED"
        verified = False
    else:
        verdict = "PREGAME_ACTUAL_START_CONFIRMED_ARCHIVE_ONLY"
        verified = True

    return {
        **base,
        "actual_start_status": "VERIFIED_SOURCE_ATTACHED",
        "actual_start_time": actual.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actual_start_source": source,
        "actual_start_retrieved_at": retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pregame_actual_start_verified": verified,
        "adjudication": verdict,
        "eligible_for_promotion_evidence": False,
    }
