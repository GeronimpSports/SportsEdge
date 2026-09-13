#!/usr/bin/env python3
"""Audit MLB V8 forward decision evidence for replay-ready PIT input provenance.

This audit is classification-only. It never creates Model_P, promotion authority,
market eligibility, Truth Gate PASS, an edge floor, or OFFICIAL status.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

DEFAULT_ROOT = Path("artifacts/mlb_v8_forward")
REQUIRED_BINDINGS = ("lineup", "starter")


def _hex64(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if len(text) != 64:
        return False
    try:
        int(text, 16)
    except ValueError:
        return False
    return True


def _parse_ts(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(timezone.utc)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _binding_status(payload: dict[str, Any], record_path: Path) -> tuple[bool, list[str]]:
    failures: list[str] = []
    provenance = payload.get("source_provenance")
    if not isinstance(provenance, dict):
        return False, ["SOURCE_PROVENANCE_MISSING"]
    try:
        captured_at = _parse_ts(payload.get("captured_at"))
    except Exception:
        return False, ["CAPTURE_TIMESTAMP_INVALID"]

    for kind in REQUIRED_BINDINGS:
        prefix = f"{kind}_snapshot"
        rel = provenance.get(f"{prefix}_path")
        digest = provenance.get(f"{prefix}_sha256")
        observed = provenance.get(f"{prefix}_observed_at")
        if not rel:
            failures.append(f"{kind.upper()}_RAW_PATH_MISSING")
            continue
        if not _hex64(digest):
            failures.append(f"{kind.upper()}_SHA256_MISSING_OR_INVALID")
            continue
        raw_path = Path(str(rel))
        if not raw_path.is_absolute():
            raw_path = record_path.parents[4] / raw_path
        if not raw_path.is_file():
            failures.append(f"{kind.upper()}_RAW_BYTES_MISSING")
            continue
        if _sha(raw_path.read_bytes()) != str(digest).lower():
            failures.append(f"{kind.upper()}_RAW_SHA256_MISMATCH")
            continue
        try:
            observed_at = _parse_ts(observed)
        except Exception:
            failures.append(f"{kind.upper()}_OBSERVED_AT_INVALID")
            continue
        if observed_at > captured_at:
            failures.append(f"{kind.upper()}_OBSERVED_AFTER_DECISION_CAPTURE")

    return not failures, failures


def audit(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*/decision/*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("payload missing")
            ready, failures = _binding_status(payload, path)
            rows.append({
                "path": path.as_posix(),
                "game_id": str(payload.get("game_id") or ""),
                "captured_at": payload.get("captured_at"),
                "replay_ready_pit": ready,
                "failures": failures,
            })
        except Exception as exc:
            rows.append({
                "path": path.as_posix(),
                "game_id": "",
                "captured_at": None,
                "replay_ready_pit": False,
                "failures": [f"RECORD_INVALID:{type(exc).__name__}:{exc}"],
            })
    ready = sum(bool(row["replay_ready_pit"]) for row in rows)
    return {
        "schema": "SPORTSEDGE_MLB_V8_FORWARD_PIT_PROVENANCE_AUDIT_V1",
        "decision_records": len(rows),
        "replay_ready_records": ready,
        "blocked_records": len(rows) - ready,
        "status": "PASS" if rows and ready == len(rows) else "BLOCKED",
        "promotion_authority": False,
        "eligibility_changed": False,
        "edge_floor_changed": False,
        "official_status_granted": False,
        "records": rows,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "artifacts" / "mlb_v8_forward"
        record_dir = root / "2026-09-12" / "123" / "decision"
        record_dir.mkdir(parents=True)
        source_root = root.parent
        lineup = b'{"game_id":"123","lineup":[1,2,3]}'
        starter = b'{"game_id":"123","starters":[10,20]}'
        lineup_rel = "pit_raw/123/lineup.json"
        starter_rel = "pit_raw/123/starter.json"
        (source_root / lineup_rel).parent.mkdir(parents=True)
        (source_root / lineup_rel).write_bytes(lineup)
        (source_root / starter_rel).write_bytes(starter)
        payload = {
            "game_id": "123",
            "captured_at": "2026-09-12T23:30:00+00:00",
            "source_provenance": {
                "lineup_snapshot_path": lineup_rel,
                "lineup_snapshot_sha256": _sha(lineup),
                "lineup_snapshot_observed_at": "2026-09-12T23:29:00+00:00",
                "starter_snapshot_path": starter_rel,
                "starter_snapshot_sha256": _sha(starter),
                "starter_snapshot_observed_at": "2026-09-12T23:28:00+00:00",
            },
        }
        path = record_dir / "record.json"
        path.write_text(json.dumps({"payload": payload}), encoding="utf-8")
        report = audit(root)
        assert report["status"] == "PASS"
        assert report["replay_ready_records"] == 1
        payload["source_provenance"].pop("starter_snapshot_sha256")
        path.write_text(json.dumps({"payload": payload}), encoding="utf-8")
        blocked = audit(root)
        assert blocked["status"] == "BLOCKED"
        assert "STARTER_SHA256_MISSING_OR_INVALID" in blocked["records"][0]["failures"]
    print(json.dumps({"status": "SELF_TEST_OK", "promotion_authority": False}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    report = audit(args.root)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
