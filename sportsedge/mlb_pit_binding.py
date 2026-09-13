from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class MLBPITBindingError(ValueError):
    pass


def _parse_ts(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MLBPITBindingError("PIT_SOURCE_TIMESTAMP_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise MLBPITBindingError("PIT_SOURCE_TIMESTAMP_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise MLBPITBindingError(f"PIT_SOURCE_FILE_MISSING:{path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_record(record: Mapping[str, Any], *, captured_at: datetime) -> dict[str, Any]:
    path = Path(str(record.get("path") or ""))
    expected = str(record.get("sha256") or "").lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise MLBPITBindingError("PIT_SOURCE_SHA256_INVALID")
    actual = _sha256_file(path)
    if actual != expected:
        raise MLBPITBindingError(f"PIT_SOURCE_SHA256_MISMATCH:{path}")
    observed = _parse_ts(record.get("observed_at_utc"))
    if observed > captured_at:
        raise MLBPITBindingError("PIT_SOURCE_OBSERVED_AFTER_DECISION_CAPTURE")
    out = dict(record)
    out["path"] = str(path)
    out["sha256"] = actual
    out["observed_at_utc"] = observed.isoformat()
    return out


def _schedule_contains_game(path: Path, game_pk: int) -> bool:
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except Exception as exc:
        raise MLBPITBindingError("PIT_SCHEDULE_RAW_JSON_INVALID") from exc
    for date_block in payload.get("dates") or []:
        for game in date_block.get("games") or []:
            try:
                if int(game.get("gamePk")) == game_pk:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def bind_v8_game_sources(
    card: Mapping[str, Any],
    *,
    game_id: str,
    captured_at: datetime,
) -> dict[str, Any]:
    """Return immutable same-fetch lineup/starter provenance for one V8 decision.

    This function never refetches or backfills. It can only bind files named in the
    card's same-fetch manifest. Multiple plausible snapshots are rejected because
    the final inference source would be ambiguous.
    """
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise MLBPITBindingError("DECISION_CAPTURE_TIMESTAMP_TIMEZONE_REQUIRED")
    captured = captured_at.astimezone(timezone.utc)
    manifest = card.get("pit_source_capture")
    if not isinstance(manifest, Mapping):
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_MANIFEST_MISSING")
    if manifest.get("schema") != "MLB_SAME_FETCH_PIT_SOURCE_CAPTURE_V1":
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_SCHEMA_INVALID")
    if manifest.get("capture_semantics") != "SAME_RESPONSE_BYTES_CONSUMED_BY_MODEL":
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_SEMANTICS_INVALID")
    if manifest.get("promotion_authority") is not False:
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_AUTHORITY_INVALID")
    if manifest.get("retroactive_point_in_time_claim") is not False:
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_RETROACTIVE_CLAIM_INVALID")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise MLBPITBindingError("PIT_SOURCE_CAPTURE_RECORDS_INVALID")
    try:
        game_pk = int(game_id)
    except (TypeError, ValueError) as exc:
        raise MLBPITBindingError("PIT_SOURCE_GAME_ID_INVALID") from exc

    schedules = []
    boxscores = []
    for raw in records:
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("source_kind") or "")
        if kind == "MLB_STATSAPI_SCHEDULE":
            schedules.append(_valid_record(raw, captured_at=captured))
        elif kind == "MLB_STATSAPI_BOXSCORE":
            try:
                record_game_pk = int(raw.get("game_pk"))
            except (TypeError, ValueError):
                continue
            if record_game_pk == game_pk:
                boxscores.append(_valid_record(raw, captured_at=captured))

    schedules = [record for record in schedules if _schedule_contains_game(Path(record["path"]), game_pk)]
    if len(schedules) != 1:
        raise MLBPITBindingError(f"PIT_STARTER_SOURCE_AMBIGUOUS_OR_MISSING:{len(schedules)}")
    if len(boxscores) != 1:
        raise MLBPITBindingError(f"PIT_LINEUP_SOURCE_AMBIGUOUS_OR_MISSING:{len(boxscores)}")

    starter = schedules[0]
    lineup = boxscores[0]
    return {
        "pit_capture_schema": manifest["schema"],
        "pit_capture_semantics": manifest["capture_semantics"],
        "starter_snapshot_path": starter["path"],
        "starter_snapshot_sha256": starter["sha256"],
        "starter_observed_at_utc": starter["observed_at_utc"],
        "lineup_snapshot_path": lineup["path"],
        "lineup_snapshot_sha256": lineup["sha256"],
        "lineup_observed_at_utc": lineup["observed_at_utc"],
        "pit_binding_promotion_authority": False,
        "pit_binding_retroactive_claim": False,
    }
