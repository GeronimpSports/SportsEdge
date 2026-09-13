"""Model-free two-sided closing-line archive for NFL, CFB and MLB.

CLOSING_LINE_ARCHIVE_V1. This lane observes prices only. It produces no
Model_P, no decision, and no evidence_unit_id, and it is labelled
NOT_EVIDENCE on every row. It cannot start or extend a promotion evidence
clock and is never a substitute for FOOTBALL_FORWARD_CAPTURE_V2 or the MLB
replay packages.

A single paid fetch may satisfy multiple overlapping capture windows. Those
window rows are labels over one physical observation and therefore share one
capture_id and fetch_sha256. Provider commence_time remains only a scheduled
start guard; every row records that guard and its known failure modes.

Credit discipline: the per-sport event index (/v4/sports/{key}/events) does
not consume an Odds API credit, so it is used as a free gate. The paid odds
endpoint is called only for a sport that currently has at least one event
inside a configured window.

Exit codes: 0 = ran (captured or nothing due), 2 = failed closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

UTC = timezone.utc
API_ROOT = "https://api.the-odds-api.com/v4"
SCHEMA_VERSION = "CLOSING_LINE_ARCHIVE_ROW_V2"
DEFAULT_POLICY_PATH = "config/closing_line_archive_policy_v1.json"
START_GUARD_SCHEDULED = "SCHEDULED_COMMENCE_ONLY"
START_GUARD_FAILURE_MODES = (
    "ACTUAL_START_EARLIER_THAN_SCHEDULED_POST_START_ADMISSION_RISK",
    "ACTUAL_START_LATER_THAN_SCHEDULED_PRESTART_DATA_LOSS_RISK",
)

KEY_ENV_VARS = (
    "SPORTSEDGE_ODDS_API_KEY",
    "SPORTSEDGE_ODDS_API_KEY_2",
    "SPORTSEDGE_ODDS_API_KEY_3",
    "SPORTSEDGE_ODDS_API_KEY_4",
)


class ArchiveError(RuntimeError):
    """Fail-closed error. Never downgraded to a warning."""


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if payload.get("policy_id") != "CLOSING_LINE_ARCHIVE_V1":
        raise ArchiveError("CLOSING_LINE_ARCHIVE_POLICY_ID_MISMATCH")
    if payload.get("evidence_class") != "NOT_EVIDENCE":
        raise ArchiveError("CLOSING_LINE_ARCHIVE_EVIDENCE_CLASS_INVALID")
    if payload.get("promotion_authority") is not False:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_PROMOTION_AUTHORITY_INVALID")
    return payload


def _parse_ts(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_TIMESTAMP_MISSING")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_TIMESTAMP_NAIVE")
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def api_keys() -> list[str]:
    keys = [os.environ.get(name, "").strip() for name in KEY_ENV_VARS]
    present = [key for key in keys if key]
    if not present:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_NO_ODDS_API_KEY")
    return present


def _default_opener(url: str, timeout: int = 30) -> Any:
    return urllib.request.urlopen(url, timeout=timeout)


def _get_json(url: str, opener: Callable[..., Any]) -> Any:
    try:
        with opener(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ArchiveError(f"CLOSING_LINE_ARCHIVE_HTTP_{exc.code}") from exc
    except Exception as exc:
        raise ArchiveError("CLOSING_LINE_ARCHIVE_FETCH_FAILED") from exc


def _try_keys(build_url: Callable[[str], str], keys: Iterable[str], opener: Callable[..., Any]) -> Any:
    last: ArchiveError | None = None
    for key in keys:
        try:
            return _get_json(build_url(key), opener)
        except ArchiveError as exc:
            last = exc
            continue
    raise last or ArchiveError("CLOSING_LINE_ARCHIVE_FETCH_FAILED")


def fetch_event_index(sport_key: str, keys: Iterable[str], opener: Callable[..., Any]) -> list[dict[str, Any]]:
    """Free endpoint. Used purely to decide whether a paid call is warranted."""

    def build(key: str) -> str:
        query = urllib.parse.urlencode({"apiKey": key})
        return f"{API_ROOT}/sports/{sport_key}/events?{query}"

    payload = _try_keys(build, keys, opener)
    if not isinstance(payload, list):
        raise ArchiveError("CLOSING_LINE_ARCHIVE_EVENT_INDEX_MALFORMED")
    return [dict(item) for item in payload]


def fetch_odds(sport_key: str, policy: Mapping[str, Any], keys: Iterable[str], opener: Callable[..., Any]) -> list[dict[str, Any]]:
    def build(key: str) -> str:
        query = urllib.parse.urlencode(
            {
                "apiKey": key,
                "regions": policy["regions"],
                "markets": ",".join(policy["markets"]),
                "oddsFormat": policy["odds_format"],
                "bookmakers": ",".join(policy["books"]),
            }
        )
        return f"{API_ROOT}/sports/{sport_key}/odds?{query}"

    payload = _try_keys(build, keys, opener)
    if not isinstance(payload, list):
        raise ArchiveError("CLOSING_LINE_ARCHIVE_ODDS_MALFORMED")
    return [dict(item) for item in payload]


def windows_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every matching capture-window label in policy declaration order."""
    lead_minutes = (start - now).total_seconds() / 60.0
    if lead_minutes <= 0:
        return ()
    matches: list[str] = []
    for name, bounds in policy["windows"].items():
        if bounds["min_minutes_before_start"] <= lead_minutes <= bounds["max_minutes_before_start"]:
            matches.append(name)
    return tuple(matches)


def window_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> str | None:
    """Compatibility helper returning the first matching window."""
    matches = windows_for(start, now, policy)
    return matches[0] if matches else None


def due_events(events: Iterable[Mapping[str, Any]], now: datetime, policy: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """Map event_id -> all capture-window memberships currently satisfied."""
    due: dict[str, tuple[str, ...]] = {}
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        try:
            start = _parse_ts(event.get("commence_time"))
        except ArchiveError:
            continue
        memberships = windows_for(start, now, policy)
        if memberships:
            due[event_id] = memberships
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return rows plus skips; overlapping windows share one capture identity."""
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    captured_at = _iso(now)
    payload = list(odds_payload)
    fetch_sha256 = _canonical_fetch_sha256(payload)
    capture_id = _capture_id(sport_key, captured_at, fetch_sha256)

    for event in payload:
        event_id = str(event.get("id") or "").strip()
        if event_id not in due:
            continue
        memberships = _normalize_memberships(due[event_id])
        start = _parse_ts(event.get("commence_time"))
        lead_minutes = (start - now).total_seconds() / 60.0
        if start <= now:
            skipped.append(
                {
                    "event_id": event_id,
                    "reason": "EVENT_ALREADY_STARTED",
                    "capture_id": capture_id,
                    "fetch_sha256": fetch_sha256,
                    "start_guard": START_GUARD_SCHEDULED,
                    "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
                }
            )
            continue

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
                                "scheduled_lead_minutes": round(lead_minutes, 6),
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


def append_rows(rows: Iterable[Mapping[str, Any]], out_dir: Path, policy: Mapping[str, Any]) -> dict[str, int]:
    """Append-only NDJSON, partitioned by sport and UTC date."""
    written: dict[str, int] = {}
    for row in rows:
        date = str(row["commence_time"])[:10]
        target = out_dir / policy["persistence"]["path_template"].format(
            sport_key=row["sport_key"], date=date
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        written[str(target)] = written.get(str(target), 0) + 1
    return written


def run(
    *,
    now: datetime,
    policy: Mapping[str, Any],
    out_dir: Path,
    keys: list[str],
    opener: Callable[..., Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
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
        due = due_events(events, now, policy)
        entry: dict[str, Any] = {
            "sport_key": sport_key,
            "events_in_index": len(events),
            "events_due": len(due),
            "window_memberships_due": sum(len(x) for x in due.values()),
            "windows": sorted({window for memberships in due.values() for window in memberships}),
            "paid_call_made": False,
            "rows_written": 0,
            "skipped": [],
            "start_guard": START_GUARD_SCHEDULED,
            "guard_failure_modes": list(START_GUARD_FAILURE_MODES),
        }
        if due and not dry_run:
            odds_payload = fetch_odds(sport_key, policy, keys, opener)
            entry["paid_call_made"] = True
            rows, skipped = build_rows(sport_key, odds_payload, due, now, policy)
            written = append_rows(rows, out_dir, policy)
            entry["rows_written"] = sum(written.values())
            entry["files"] = written
            entry["skipped"] = skipped
            if rows:
                entry["capture_ids"] = sorted({row["capture_id"] for row in rows})
                entry["fetch_sha256"] = sorted({row["fetch_sha256"] for row in rows})
        report["sports"][label] = entry

    report["total_rows_written"] = sum(
        entry["rows_written"] for entry in report["sports"].values()
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=DEFAULT_POLICY_PATH)
    parser.add_argument("--out-dir", default=".", help="Repository root of the data worktree.")
    parser.add_argument("--status-out", default=None, help="Write the run report here.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use the free event index only. Never calls the paid odds endpoint.",
    )
    parser.add_argument("--now", default=None, help="Override current time (ISO-8601, testing only).")
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.policy)
        now = _parse_ts(args.now) if args.now else datetime.now(UTC)
        report = run(
            now=now,
            policy=policy,
            out_dir=Path(args.out_dir),
            keys=api_keys(),
            opener=_default_opener,
            dry_run=args.dry_run,
        )
    except ArchiveError as exc:
        failure = {"state": "BLOCKED", "reason": str(exc)}
        text = json.dumps(failure, indent=2)
        if args.status_out:
            Path(args.status_out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.status_out).write_text(text + "\n")
        print(text, file=sys.stderr)
        return 2

    text = json.dumps(report, indent=2, sort_keys=True)
    if args.status_out:
        Path(args.status_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.status_out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
