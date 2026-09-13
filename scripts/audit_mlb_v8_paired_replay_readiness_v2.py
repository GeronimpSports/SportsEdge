#!/usr/bin/env python3
"""Audit actual-start-bound MLB V8 OddsPapi decision/close evidence.

This is evidence-readiness only. It cannot create Model_P, change market
eligibility, set an edge floor, or grant promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import scripts.build_mlb_v8_oddspapi_pit as v1  # noqa: E402
import scripts.build_mlb_v8_oddspapi_pit_v2 as v2  # noqa: E402
from sportsedge.sports.mlb.paired_replay_readiness import audit_paired_replay_readiness  # noqa: E402

SCHEMA = "MLB_V8_ODDSPAPI_PIT_PAIR_V2"
SOURCE = "ODDSPAPI_HISTORICAL"
PAIR_MAX_SKEW_SECONDS = 30.0
STRICT_REPLAY_MAX_AGE_SECONDS = 180.0
DEFAULT_ROOT = Path("artifacts/mlb_v8_replay_sources/ODDSPAPI_HISTORICAL")
DEFAULT_INPUT = Path("artifacts/mlb_v8_replay_archive/oddspapi_pit_v2/pit_pairs.jsonl")
DEFAULT_OUTPUT = Path("artifacts/mlb_v8_replay_archive/oddspapi_pit_v2/paired_replay_readiness.json")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_sha(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def _same_number(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= 1e-12
    except (TypeError, ValueError):
        return str(a) == str(b)


def _same_price(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) <= 1e-12
    except (TypeError, ValueError):
        return False


def _raw_history_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in sorted(root.glob("????-??-??/*/history_*.json")):
        if path.name.endswith(".meta.json"):
            continue
        digest = _sha(path.read_bytes())
        index.setdefault(digest, []).append(path)
    return index


def _fixture_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in sorted(root.glob("????-??-??/*/fixture.normalized.json")):
        try:
            fixture = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        fixture_id = str(fixture.get("fixtureId") or "").strip()
        if fixture_id:
            index.setdefault(fixture_id, []).append(path)
    return index


def _catalog_by_id(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    catalog, catalog_sha = v1._load_catalog(root)
    return catalog, catalog_sha


def _reject(rejected: list[dict[str, Any]], index: int, row: dict[str, Any], *reasons: str) -> None:
    rejected.append({"index": index, "fixture_id": row.get("fixture_id"), "reasons": list(reasons)})


def _row_to_pairs(
    row: dict[str, Any], *, root: Path, history_index: dict[str, list[Path]],
    fixture_index: dict[str, list[Path]], catalog: dict[str, dict[str, Any]], catalog_sha: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    reasons: list[str] = []
    if row.get("schema") != SCHEMA:
        reasons.append("SCHEMA_MISMATCH")
    if row.get("source") != SOURCE:
        reasons.append("SOURCE_MISMATCH")
    if row.get("promotion_authority") is not False:
        reasons.append("PROMOTION_AUTHORITY_MUST_BE_FALSE")
    for field in ("same_book_same_threshold_bound", "close_available", "close_after_decision", "close_before_actual_first_play", "close_same_book_same_threshold"):
        if row.get(field) is not True:
            reasons.append(f"{field.upper()}_REQUIRED")
    for field in ("history_sha256", "market_catalog_sha256", "actual_start_feed_sha256", "threshold_binding_sha256"):
        if not _valid_sha(row.get(field)):
            reasons.append(f"{field.upper()}_INVALID")
    if reasons:
        return [], reasons

    fixture_id = str(row.get("fixture_id") or "")
    fixture_paths = fixture_index.get(fixture_id, [])
    if len(fixture_paths) != 1:
        return [], ["FIXTURE_ID_NOT_UNIQUE_IN_RAW_ARCHIVE"]
    fixture_path = fixture_paths[0]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    att = v2.attestation(root, fixture_path, fixture)
    if att is None:
        return [], ["ACTUAL_START_ATTESTATION_INVALID"]
    if str(att.get("actual_first_play_utc")) != str(row.get("actual_first_play_utc")):
        reasons.append("ACTUAL_START_TIMESTAMP_MISMATCH")
    if str(att.get("game_feed_payload_sha256")) != str(row.get("actual_start_feed_sha256")):
        reasons.append("ACTUAL_START_FEED_SHA_MISMATCH")
    if str(att.get("game_feed_payload_path")) != str(row.get("actual_start_feed_path")):
        reasons.append("ACTUAL_START_FEED_PATH_MISMATCH")

    market_id = str(row.get("market_id") or "")
    info = catalog.get(market_id)
    if info is None:
        reasons.append("MARKET_ID_NOT_IN_HASH_BOUND_CATALOG")
    elif str(row.get("market_catalog_sha256")) != catalog_sha:
        reasons.append("MARKET_CATALOG_SHA_MISMATCH")
    else:
        if not _same_number(info.get("handicap"), row.get("handicap")):
            reasons.append("HANDICAP_CATALOG_MISMATCH")
        if str(info.get("period")) != str(row.get("period")):
            reasons.append("PERIOD_CATALOG_MISMATCH")
        if str(info.get("marketType")) != str(row.get("market_type")):
            reasons.append("MARKET_TYPE_CATALOG_MISMATCH")
        expected_outcomes = tuple(sorted(str(x) for x in v1._catalog_outcomes(info).keys()))
        row_outcomes = tuple(sorted((str(row.get("outcome_a_id") or ""), str(row.get("outcome_b_id") or ""))))
        if expected_outcomes != row_outcomes:
            reasons.append("OUTCOME_IDS_CATALOG_MISMATCH")
        else:
            expected_binding = v2.binding(str(row.get("bookmaker")), market_id, str(row.get("player_id")), info, row_outcomes)
            if expected_binding != str(row.get("threshold_binding_sha256")):
                reasons.append("THRESHOLD_BINDING_SHA_MISMATCH")

    history_sha = str(row.get("history_sha256"))
    history_paths = history_index.get(history_sha, [])
    if len(history_paths) != 1:
        reasons.append("HISTORY_SHA_NOT_UNIQUE_IN_RAW_ARCHIVE")
    if reasons:
        return [], reasons

    raw = history_paths[0].read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if str(payload.get("fixtureId") or "") != fixture_id:
        return [], ["RAW_HISTORY_FIXTURE_ID_MISMATCH"]
    try:
        market = payload["bookmakers"][str(row["bookmaker"])]["markets"][market_id]
        outcomes_map = market["outcomes"]
        aid, bid = str(row["outcome_a_id"]), str(row["outcome_b_id"])
        player_id = str(row["player_id"])
        left = v1._timeline(outcomes_map[aid], player_id)
        right = v1._timeline(outcomes_map[bid], player_id)
    except (KeyError, TypeError):
        return [], ["RAW_HISTORY_IDENTITY_PATH_MISSING"]

    actual = v1._parse_ts(row["actual_first_play_utc"])
    target = actual - __import__("datetime").timedelta(minutes=v1.DECISION_MINUTES)
    decision = v1._state_pair(left, right, cutoff=target, max_age_seconds=v1.CANONICAL_TOLERANCE_SECONDS)
    close = v1._state_pair(left, right, cutoff=actual - __import__("datetime").timedelta(microseconds=1), max_age_seconds=None)
    if decision is None:
        return [], ["RAW_DECISION_PAIR_NOT_REPRODUCIBLE"]
    if close is None:
        return [], ["RAW_CLOSE_PAIR_NOT_REPRODUCIBLE"]
    a, b = decision
    ca, cb = close
    if min(ca["_ts"], cb["_ts"]) <= max(a["_ts"], b["_ts"]):
        return [], ["RAW_CLOSE_NOT_AFTER_DECISION"]

    decision_age = max((target - a["_ts"]).total_seconds(), (target - b["_ts"]).total_seconds())
    decision_skew = abs((a["_ts"] - b["_ts"]).total_seconds())
    close_skew = abs((ca["_ts"] - cb["_ts"]).total_seconds())
    if decision_age > STRICT_REPLAY_MAX_AGE_SECONDS:
        reasons.append("DECISION_QUOTE_NOT_REPLAY_FRESH_180S")
    if decision_skew > PAIR_MAX_SKEW_SECONDS:
        reasons.append("DECISION_PAIR_SKEW_INVALID")
    if close_skew > PAIR_MAX_SKEW_SECONDS:
        reasons.append("CLOSE_PAIR_SKEW_INVALID")

    expected = {
        "outcome_a_quote_utc": a["_ts"].isoformat(), "outcome_b_quote_utc": b["_ts"].isoformat(),
        "close_outcome_a_quote_utc": ca["_ts"].isoformat(), "close_outcome_b_quote_utc": cb["_ts"].isoformat(),
    }
    for field, value in expected.items():
        if str(row.get(field)) != value:
            reasons.append(f"{field.upper()}_RAW_MISMATCH")
    expected_prices = {
        "outcome_a_decimal": a["_price"], "outcome_b_decimal": b["_price"],
        "close_outcome_a_decimal": ca["_price"], "close_outcome_b_decimal": cb["_price"],
    }
    for field, value in expected_prices.items():
        if not _same_price(row.get(field), value):
            reasons.append(f"{field.upper()}_RAW_MISMATCH")
    if max(ca["_ts"], cb["_ts"]) >= actual:
        reasons.append("RAW_CLOSE_NOT_BEFORE_ACTUAL_FIRST_PLAY")
    if reasons:
        return [], reasons

    identity = {
        "event_id": fixture_id,
        "market": market_id,
        "book": str(row["bookmaker"]),
        "threshold": row.get("handicap"),
        "provenance": "oddspapi_historical_provider_snapshot_actual_start_bound",
        "source_sha256": history_sha,
    }
    pairs: list[dict[str, Any]] = []
    for side, d, c in (("a", a, ca), ("b", b, cb)):
        selection = str(row.get(f"outcome_{side}_id") or row.get(f"outcome_{side}_name") or "")
        pairs.append({
            "event_start": actual.isoformat(),
            "decision": {**identity, "selection": selection, "observed_at": d["_ts"].isoformat(), "price": d["_price"]},
            "close": {**identity, "selection": selection, "observed_at": c["_ts"].isoformat(), "price": c["_price"]},
        })
    return pairs, []


def audit_rows(rows: Iterable[dict[str, Any]], root: Path) -> dict[str, Any]:
    history_index = _raw_history_index(root)
    fixture_index = _fixture_index(root)
    try:
        catalog, catalog_sha = _catalog_by_id(root)
    except Exception as exc:
        return {
            "schema_version": "mlb_v8_oddspapi_actual_start_replay_readiness_v2",
            "status": "BLOCKED_PAIRED_MARKET_EVIDENCE",
            "promotion_authority": False,
            "may_change_market_eligibility": False,
            "source_archive_error": f"{type(exc).__name__}:{exc}",
            "valid_pair_count": 0,
            "invalid_pair_count": 0,
        }
    pairs: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        normalized, reasons = _row_to_pairs(
            row, root=root, history_index=history_index, fixture_index=fixture_index,
            catalog=catalog, catalog_sha=catalog_sha,
        )
        if reasons:
            _reject(rejected, index, row, *reasons)
        else:
            pairs.extend(normalized)
    result = audit_paired_replay_readiness(pairs)
    if rejected:
        result["status"] = "BLOCKED_PAIRED_MARKET_EVIDENCE"
    result.update({
        "normalized_source_schema": SCHEMA,
        "normalized_source": SOURCE,
        "actual_start_bound": True,
        "raw_history_reverified": True,
        "catalog_threshold_binding_reverified": True,
        "strict_replay_max_age_seconds": STRICT_REPLAY_MAX_AGE_SECONDS,
        "pair_max_skew_seconds": PAIR_MAX_SKEW_SECONDS,
        "source_row_count": len(list(rows)) if isinstance(rows, list) else None,
        "rejected_source_row_count": len(rejected),
        "source_row_rejections": rejected,
        "promotion_authority": False,
        "may_change_market_eligibility": False,
    })
    return result


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"ROW_NOT_OBJECT:{number}")
        rows.append(value)
    return rows


def self_test() -> int:
    # Contract-level checks that do not fabricate provider evidence.
    assert _valid_sha("a" * 64)
    assert not _valid_sha("x" * 64)
    assert _same_number(7.5, "7.5")
    assert _same_price(1.91, "1.91")
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td)
        blocked = audit_rows([], empty)
        assert blocked["status"] == "BLOCKED_PAIRED_MARKET_EVIDENCE"
        assert blocked["promotion_authority"] is False
        assert blocked["may_change_market_eligibility"] is False
    print(json.dumps({
        "status": "SELF_TEST_OK",
        "schema": SCHEMA,
        "actual_start_required": True,
        "raw_history_reverification_required": True,
        "catalog_threshold_binding_reverification_required": True,
        "strict_replay_max_age_seconds": STRICT_REPLAY_MAX_AGE_SECONDS,
        "promotion_authority": False,
    }, sort_keys=True))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--require-ready", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    try:
        rows = _load_jsonl(args.input)
        result = audit_rows(rows, args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema_version": "mlb_v8_oddspapi_actual_start_replay_readiness_v2",
            "status": "BLOCKED_PAIRED_MARKET_EVIDENCE",
            "promotion_authority": False,
            "may_change_market_eligibility": False,
            "input_error": f"{type(exc).__name__}:{exc}",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if args.require_ready and result.get("status") != "READY_FOR_REPLAY":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
