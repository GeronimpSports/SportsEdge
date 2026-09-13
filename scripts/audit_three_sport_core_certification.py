#!/usr/bin/env python3
"""Fail-closed audit of core NFL/CFB/MLB certification readiness.

This tool summarizes existing evidence only. It never creates Model_P, changes
eligibility, sets an edge floor, or grants Truth Gate/OFFICIAL authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CORE_MLB = ("MONEYLINE", "RUN_LINE", "TOTALS")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _cfb_snapshot_status(snapshot: Path) -> tuple[str | None, str | None]:
    """Return explicit forward-snapshot classification without inventing readiness.

    Older capture layouts may carry a root readiness.json. The current game-source
    capture stores its authority/classification at capture/classification.json.
    Neither form is allowed to imply historical PIT or promotion authority.
    """
    readiness = snapshot / "readiness.json"
    if readiness.is_file():
        payload = _load(readiness)
        return payload.get("status"), "readiness.json"

    classification = snapshot / "capture/classification.json"
    if classification.is_file():
        payload = _load(classification)
        return payload.get("pit_classification") or payload.get("capture_classification"), "capture/classification.json"

    return None, None


def audit(data_root: Path) -> dict:
    result = {
        "schema_version": "SPORTSEDGE_THREE_SPORT_CORE_CERTIFICATION_AUDIT_V1",
        "authority": {
            "model_p_created": False,
            "truth_gate_changed": False,
            "eligibility_changed": False,
            "edge_floor_changed": False,
            "official_bet_created": False,
        },
        "sports": {},
    }

    nfl_forward = data_root / "runtime/nfl-forward"
    nfl_entries = sorted(p.name for p in nfl_forward.iterdir()) if nfl_forward.is_dir() else []
    result["sports"]["NFL"] = {
        "core_markets": ["MONEYLINE", "SPREAD", "TOTAL"],
        "forward_archive_present": bool(nfl_entries),
        "forward_archive_entry_count": len(nfl_entries),
        "status": "EVIDENCE_PRESENT_NOT_CERTIFIED_BY_THIS_AUDIT" if nfl_entries else "BLOCKED_NO_FORWARD_ARCHIVE",
        "next_gate": "source-bound promotion evidence + current-market decision/close pairing; failed candidates remain failed",
    }

    cfb_forward = data_root / "history/cfb/forward-pit"
    cfb_snapshots = sorted(p for p in cfb_forward.iterdir() if p.is_dir()) if cfb_forward.is_dir() else []
    cfb_latest = cfb_snapshots[-1] if cfb_snapshots else None
    cfb_snapshot_status = None
    cfb_snapshot_status_source = None
    if cfb_latest is not None:
        cfb_snapshot_status, cfb_snapshot_status_source = _cfb_snapshot_status(cfb_latest)
    cfb_hist = data_root / "history/cfb/pit"
    result["sports"]["CFB"] = {
        "core_markets": ["MONEYLINE", "SPREAD", "TOTAL"],
        "forward_pit_snapshot_count": len(cfb_snapshots),
        "latest_forward_pit": cfb_latest.name if cfb_latest else None,
        "latest_forward_pit_status": cfb_snapshot_status,
        "latest_forward_pit_status_source": cfb_snapshot_status_source,
        "historical_pit_training_bundle_present": cfb_hist.exists(),
        "status": "BLOCKED_HISTORICAL_PIT_TRAINING_BUNDLE_MISSING" if not cfb_hist.exists() else "HISTORICAL_PIT_PRESENT_REQUIRES_VALIDATION",
        "next_gate": "historical PIT/temporal training evidence, then calibration/holdout and paired forward decision-close evidence",
    }

    mlb_status_path = data_root / "runtime/model-validation/SUMMARY/latest/derived_status.json"
    mlb = _load(mlb_status_path) if mlb_status_path.is_file() else {}
    markets = mlb.get("markets", {}) if isinstance(mlb, dict) else {}
    core = {}
    for name in CORE_MLB:
        row = markets.get(name, {})
        core[name] = {
            gate: row.get(gate, {}).get("status")
            for gate in (
                "historical_point_in_time",
                "untouched_holdout",
                "calibration",
                "settlement_semantics",
                "production_parity",
                "forward_evidence",
            )
        }
    raw_odds = data_root / "archive/raw_odds"
    closing = data_root / "archive/closing-lines"
    all_core_pass = bool(core) and all(v == "PASS" for row in core.values() for v in row.values())
    result["sports"]["MLB"] = {
        "core_markets": list(CORE_MLB),
        "six_gate_status": core,
        "raw_odds_archive_present": raw_odds.exists(),
        "closing_line_archive_present": closing.exists(),
        "status": "CORE_GATES_PASS" if all_core_pass else "BLOCKED_CORE_GATES_INCOMPLETE",
        "next_gate": "genuine PIT decision/close evidence, untouched holdout, calibration, production parity and forward/CLV validation",
    }

    result["all_three_core_certified"] = all(
        result["sports"][sport]["status"] in {"CORE_GATES_PASS", "CERTIFIED"}
        for sport in ("NFL", "CFB", "MLB")
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    report = audit(args.data_root)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
