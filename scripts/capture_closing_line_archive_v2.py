"""CLOSING_LINE_ARCHIVE_V2: model-free, append-only, NOT_EVIDENCE prices.

Provider commence_time is only a capture-planning hint. Every row remains
UNADJUDICATED until a separate immutable actual-start attestation exists.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from scripts import capture_closing_line_archive as v1
except ModuleNotFoundError:  # direct execution: python scripts/capture_closing_line_archive_v2.py
    import capture_closing_line_archive as v1

ArchiveError = v1.ArchiveError
_parse_ts = v1._parse_ts
_iso = v1._iso
api_keys = v1.api_keys
_default_opener = v1._default_opener
fetch_event_index = v1.fetch_event_index
fetch_odds = v1.fetch_odds

DEFAULT_POLICY_PATH = "config/closing_line_archive_policy_v2.json"
SCHEMA_VERSION = "CLOSING_LINE_ARCHIVE_ROW_V2"


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if payload.get("policy_id") != "CLOSING_LINE_ARCHIVE_V2":
        raise ArchiveError("CLOSING_LINE_ARCHIVE_POLICY_ID_MISMATCH")
    if payload.get("evidence_class") != "NOT_EVIDENCE" or payload.get("promotion_authority") is not False:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_AUTHORITY_INVALID")
    windows = payload.get("windows") or {}
    priority = payload.get("window_priority") or []
    if len(priority) != len(set(priority)) or set(priority) != set(windows):
        raise ArchiveError("CLOSING_LINE_ARCHIVE_WINDOW_PRIORITY_INVALID")
    return payload


def _in_window(lead: float, bounds: Mapping[str, Any]) -> bool:
    low = float(bounds["min_lead_minutes"])
    high = float(bounds["max_lead_minutes"])
    lower = lead >= low if bounds.get("min_inclusive", True) else lead > low
    upper = lead <= high if bounds.get("max_inclusive", True) else lead < high
    return lower and upper


def window_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> str | None:
    lead = (start - now).total_seconds() / 60.0
    for name in policy["window_priority"]:
        if _in_window(lead, policy["windows"][name]):
            return name
    return None


def due_events(events: Iterable[Mapping[str, Any]], now: datetime, policy: Mapping[str, Any]) -> dict[str, str]:
    due: dict[str, str] = {}
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        try:
            start = _parse_ts(event.get("commence_time"))
        except ArchiveError:
            continue
        window = window_for(start, now, policy)
        if window:
            due[event_id] = window
    return due


def build_rows(sport_key: str, odds_payload: Iterable[Mapping[str, Any]], due: Mapping[str, str], now: datetime, policy: Mapping[str, Any]):
    rows, skipped = [], []
    captured_at = _iso(now)
    for event in odds_payload:
        event_id = str(event.get("id") or "").strip()
        if event_id not in due:
            continue
        start = _parse_ts(event.get("commence_time"))
        lead = (start - now).total_seconds() / 60.0
        for bookmaker in event.get("bookmakers") or []:
            book = str(bookmaker.get("key") or "").strip().lower()
            if book not in policy["books"]:
                continue
            for market in bookmaker.get("markets") or []:
                market_key = str(market.get("key") or "").strip().lower()
                if market_key not in policy["markets"]:
                    continue
                outcomes = list(market.get("outcomes") or [])
                if len(outcomes) < 2:
                    skipped.append({"event_id": event_id, "book": book, "market": market_key, "reason": "ONE_SIDED_QUOTE_NOT_IMPUTED"})
                    continue
                for outcome in outcomes:
                    rows.append({
                        "schema_version": SCHEMA_VERSION,
                        "policy_id": policy["policy_id"],
                        "evidence_class": "NOT_EVIDENCE",
                        "promotion_authority": False,
                        "sport_key": sport_key,
                        "event_id": event_id,
                        "commence_time": _iso(start),
                        "scheduled_lead_minutes": round(lead, 6),
                        "actual_start_status": "UNADJUDICATED",
                        "requires_start_attestation": True,
                        "home_team": event.get("home_team"),
                        "away_team": event.get("away_team"),
                        "book": book,
                        "market": market_key,
                        "outcome": outcome.get("name"),
                        "point": outcome.get("point"),
                        "price_american": outcome.get("price"),
                        "window": due[event_id],
                        "captured_at": captured_at,
                        "sides_in_market": len(outcomes),
                        "book_last_update": bookmaker.get("last_update"),
                    })
    return rows, skipped


def run(*, now: datetime, policy: Mapping[str, Any], out_dir: Path, keys: list[str], opener: Callable[..., Any], dry_run: bool = False) -> dict[str, Any]:
    report = {"policy_id": policy["policy_id"], "evidence_class": "NOT_EVIDENCE", "ran_at": _iso(now), "dry_run": dry_run, "sports": {}}
    for label, sport_key in policy["sports"].items():
        events = fetch_event_index(sport_key, keys, opener)
        due = due_events(events, now, policy)
        entry = {"sport_key": sport_key, "events_in_index": len(events), "events_due": len(due), "windows": sorted(set(due.values())), "paid_call_made": False, "rows_written": 0, "skipped": []}
        if due and not dry_run:
            odds_payload = fetch_odds(sport_key, policy, keys, opener)
            entry["paid_call_made"] = True
            rows, skipped = build_rows(sport_key, odds_payload, due, now, policy)
            written = v1.append_rows(rows, out_dir, policy)
            entry["rows_written"] = sum(written.values())
            entry["files"] = written
            entry["skipped"] = skipped
        report["sports"][label] = entry
    report["total_rows_written"] = sum(x["rows_written"] for x in report["sports"].values())
    return report


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--status-out", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        now = _parse_ts(args.now) if args.now else datetime.now(v1.UTC)
        report = run(now=now, policy=policy, out_dir=Path(args.out_dir), keys=api_keys(), opener=_default_opener, dry_run=args.dry_run)
    except ArchiveError as exc:
        report = {"state": "BLOCKED", "reason": str(exc)}
        code = 2
    else:
        code = 0
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.status_out:
        Path(args.status_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.status_out).write_text(text + "\n")
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
