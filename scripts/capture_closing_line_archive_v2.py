"""CLOSING_LINE_ARCHIVE_V2: model-free, append-only, NOT_EVIDENCE prices.

Provider commence_time is only a capture-planning hint. Every price row states
which start guard governed the fetch. This producer is scheduled-commence-only;
actual-start verification is a separate immutable attestation stream.
"""
from __future__ import annotations

import hashlib
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
SCHEMA_VERSION = "CLOSING_LINE_ARCHIVE_ROW_V3"
START_GUARD_SCHEDULED = "SCHEDULED_COMMENCE_ONLY"
START_GUARD_ACTUAL = "ACTUAL_START_VERIFIED"
START_GUARD_FAILURE_MODES = (
    "ACTUAL_START_EARLIER_THAN_SCHEDULED_POST_START_ADMISSION_RISK",
    "ACTUAL_START_LATER_THAN_SCHEDULED_PRESTART_DATA_LOSS_RISK",
)


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


def windows_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every matching window, ordered by declared priority.

    A single paid fetch may legitimately satisfy more than one archive window.
    Those rows are labels over the same observation, not independent captures.
    """
    lead = (start - now).total_seconds() / 60.0
    return tuple(
        name
        for name in policy["window_priority"]
        if _in_window(lead, policy["windows"][name])
    )


def window_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> str | None:
    """Compatibility helper: return the first matching membership, if any."""
    matches = windows_for(start, now, policy)
    return matches[0] if matches else None


def _guard_rejection(event_id: str, reason: str, *, lead: float | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event_id": event_id,
        "reason": reason,
        "start_guard": START_GUARD_SCHEDULED,
        "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
    }
    if lead is not None:
        record["scheduled_lead_minutes"] = round(lead, 6)
    return record


def classify_events(
    events: Iterable[Mapping[str, Any]],
    now: datetime,
    policy: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, ...]], list[dict[str, Any]]]:
    """Return due multi-memberships plus explicit scheduled-guard exclusions."""
    due: dict[str, tuple[str, ...]] = {}
    rejected: list[dict[str, Any]] = []
    lows = [float(bounds["min_lead_minutes"]) for bounds in policy["windows"].values()]
    highs = [float(bounds["max_lead_minutes"]) for bounds in policy["windows"].values()]
    min_lead = min(lows)
    max_lead = max(highs)

    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        try:
            start = _parse_ts(event.get("commence_time"))
        except ArchiveError:
            rejected.append(
                _guard_rejection(event_id, "SCHEDULED_COMMENCE_UNRESOLVED")
            )
            continue
        lead = (start - now).total_seconds() / 60.0
        memberships = windows_for(start, now, policy)
        if memberships:
            due[event_id] = memberships
            continue

        if lead < min_lead:
            reason = "SCHEDULED_COMMENCE_GUARD_EXPIRED_ACTUAL_START_UNKNOWN"
        elif lead > max_lead:
            reason = "OUTSIDE_CAPTURE_WINDOWS_TOO_EARLY"
        else:
            reason = "OUTSIDE_CAPTURE_WINDOWS_GAP"
        rejected.append(_guard_rejection(event_id, reason, lead=lead))

    return due, rejected


def due_events(
    events: Iterable[Mapping[str, Any]],
    now: datetime,
    policy: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    due, _ = classify_events(events, now, policy)
    return due


def _normalize_memberships(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _canonical_fetch_sha256(odds_payload: list[Mapping[str, Any]]) -> str:
    body = json.dumps(
        odds_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _capture_id(sport_key: str, captured_at: str, fetch_sha256: str) -> str:
    material = f"{sport_key}\n{captured_at}\n{fetch_sha256}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def build_rows(
    sport_key: str,
    odds_payload: Iterable[Mapping[str, Any]],
    due: Mapping[str, Any],
    now: datetime,
    policy: Mapping[str, Any],
):
    rows, skipped = [], []
    captured_at = _iso(now)
    payload = list(odds_payload)
    fetch_sha256 = _canonical_fetch_sha256(payload)
    capture_id = _capture_id(sport_key, captured_at, fetch_sha256)

    for event in payload:
        event_id = str(event.get("id") or "").strip()
        if event_id not in due:
            continue
        start = _parse_ts(event.get("commence_time"))
        lead = (start - now).total_seconds() / 60.0
        memberships = _normalize_memberships(due[event_id])
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
                    skipped.append(
                        {
                            "event_id": event_id,
                            "book": book,
                            "market": market_key,
                            "reason": "ONE_SIDED_QUOTE_NOT_IMPUTED",
                            "capture_id": capture_id,
                            "fetch_sha256": fetch_sha256,
                            "start_guard": START_GUARD_SCHEDULED,
                            "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
                        }
                    )
                    continue
                for outcome in outcomes:
                    for window in memberships:
                        rows.append(
                            {
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
                                "start_guard": START_GUARD_SCHEDULED,
                                "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
                                "capture_id": capture_id,
                                "fetch_sha256": fetch_sha256,
                                "home_team": event.get("home_team"),
                                "away_team": event.get("away_team"),
                                "book": book,
                                "market": market_key,
                                "outcome": outcome.get("name"),
                                "point": outcome.get("point"),
                                "price_american": outcome.get("price"),
                                "window": window,
                                "captured_at": captured_at,
                                "sides_in_market": len(outcomes),
                                "book_last_update": bookmaker.get("last_update"),
                            }
                        )
    return rows, skipped


def run(
    *,
    now: datetime,
    policy: Mapping[str, Any],
    out_dir: Path,
    keys: list[str],
    opener: Callable[..., Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    report = {
        "policy_id": policy["policy_id"],
        "evidence_class": "NOT_EVIDENCE",
        "ran_at": _iso(now),
        "dry_run": dry_run,
        "start_guard": START_GUARD_SCHEDULED,
        "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
        "sports": {},
    }
    for label, sport_key in policy["sports"].items():
        events = fetch_event_index(sport_key, keys, opener)
        due, event_rejections = classify_events(events, now, policy)
        windows = sorted({window for memberships in due.values() for window in memberships})
        entry = {
            "sport_key": sport_key,
            "events_in_index": len(events),
            "events_due": len(due),
            "window_memberships_due": sum(len(x) for x in due.values()),
            "windows": windows,
            "paid_call_made": False,
            "rows_written": 0,
            "skipped": [],
            "event_rejections": event_rejections,
            "start_guard": START_GUARD_SCHEDULED,
            "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
        }
        if due and not dry_run:
            odds_payload = fetch_odds(sport_key, policy, keys, opener)
            entry["paid_call_made"] = True
            rows, skipped = build_rows(sport_key, odds_payload, due, now, policy)
            written = v1.append_rows(rows, out_dir, policy)
            entry["rows_written"] = sum(written.values())
            entry["files"] = written
            entry["skipped"] = skipped
            if rows:
                entry["capture_ids"] = sorted({row["capture_id"] for row in rows})
                entry["fetch_sha256"] = sorted({row["fetch_sha256"] for row in rows})
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
        report = run(
            now=now,
            policy=policy,
            out_dir=Path(args.out_dir),
            keys=api_keys(),
            opener=_default_opener,
            dry_run=args.dry_run,
        )
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
