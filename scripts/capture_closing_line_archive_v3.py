#!/usr/bin/env python3
"""Raw-payload-preserving closing-line archive.

CLOSING_LINE_ARCHIVE_V3 keeps the V2 actual-start guard behavior and preserves
one canonical raw Odds API payload for every paid fetch. Rows remain
NOT_EVIDENCE and receive no promotion authority. The raw payload is stored only
so future sport-specific evidence admission can recompute ``fetch_sha256``
instead of trusting an unverified hash carried by a normalized row.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import scripts.capture_closing_line_archive as v1
import scripts.capture_closing_line_archive_v2 as v2

UTC = timezone.utc
RAW_ARCHIVE_VERSION = "RAW_PAYLOAD_GUARD_V3"


def canonical_payload_bytes(payload: list[Mapping[str, Any]]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def persist_raw_payload(
    sport_key: str,
    odds_payload: list[Mapping[str, Any]],
    out_dir: Path,
) -> tuple[str, str]:
    body = canonical_payload_bytes(odds_payload)
    digest = hashlib.sha256(body).hexdigest()
    rel = Path("archive") / "closing-lines" / "raw" / sport_key / f"{digest}.json"
    target = out_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != body:
            raise v1.ArchiveError("CLOSING_LINE_ARCHIVE_RAW_HASH_COLLISION")
    else:
        target.write_bytes(body)
    return rel.as_posix(), digest


def run(
    *,
    now: datetime,
    policy: Mapping[str, Any],
    out_dir: Path,
    keys: list[str],
    opener,
    dry_run: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "archive_guard_version": RAW_ARCHIVE_VERSION,
        "evidence_class": "NOT_EVIDENCE",
        "promotion_authority": False,
        "raw_payloads_preserved": True,
        "ran_at": v1._iso(now),
        "dry_run": dry_run,
        "sports": {},
    }
    for label, sport_key in policy["sports"].items():
        events = v1.fetch_event_index(sport_key, keys, opener)
        due = v2.due_events(events, now, policy)
        skipped_guard: list[dict[str, Any]] = []
        if label == "MLB" and due:
            by_id = {str(e.get("id") or ""): e for e in events}
            guarded: dict[str, str] = {}
            for event_id, window in due.items():
                guard = v2.mlb_actual_start_guard(by_id[event_id])
                if not guard.get("known") or guard.get("started"):
                    skipped_guard.append({"event_id": event_id, "window": window, **guard})
                    continue
                guarded[event_id] = window
            due = guarded

        entry: dict[str, Any] = {
            "sport_key": sport_key,
            "events_in_index": len(events),
            "events_due": len(due),
            "windows": sorted(set(due.values())),
            "paid_call_made": False,
            "rows_written": 0,
            "skipped": skipped_guard,
        }
        if due and not dry_run:
            odds_payload = v1.fetch_odds(sport_key, policy, keys, opener)
            entry["paid_call_made"] = True
            raw_path, raw_sha = persist_raw_payload(sport_key, odds_payload, out_dir)
            rows, skipped = v1.build_rows(sport_key, odds_payload, due, now, policy)
            for row in rows:
                if str(row.get("fetch_sha256") or "").lower() != raw_sha:
                    raise v1.ArchiveError("CLOSING_LINE_ARCHIVE_RAW_ROW_HASH_MISMATCH")
                row["fetch_payload_path"] = raw_path
                row["fetch_payload_sha256"] = raw_sha
                row["raw_payload_preserved"] = True
            written = v1.append_rows(rows, out_dir, policy)
            entry["rows_written"] = sum(written.values())
            entry["files"] = written
            entry["raw_payload_path"] = raw_path
            entry["raw_payload_sha256"] = raw_sha
            entry["skipped"].extend(skipped)
            if rows:
                entry["capture_ids"] = sorted({str(row["capture_id"]) for row in rows})
        report["sports"][label] = entry
    report["total_rows_written"] = sum(e["rows_written"] for e in report["sports"].values())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=v1.DEFAULT_POLICY_PATH)
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--status-out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    try:
        policy = v1.load_policy(args.policy)
        now = v1._parse_ts(args.now) if args.now else datetime.now(UTC)
        report = run(
            now=now,
            policy=policy,
            out_dir=Path(args.out_dir),
            keys=v1.api_keys(),
            opener=v1._default_opener,
            dry_run=args.dry_run,
        )
    except v1.ArchiveError as exc:
        failure = {"state": "BLOCKED", "reason": str(exc)}
        text = json.dumps(failure, indent=2, sort_keys=True)
        if args.status_out:
            Path(args.status_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.status_out).write_text(text + "\n", encoding="utf-8")
        print(text, file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.status_out:
        Path(args.status_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.status_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
