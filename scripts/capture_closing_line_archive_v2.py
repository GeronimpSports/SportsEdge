#!/usr/bin/env python3
"""Actual-start guarded closing-line archive.

Wraps CLOSING_LINE_ARCHIVE_V1 mechanics but fixes two active-lane defects:
1) overlapping windows use explicit priority (close before t0_prestart before decision),
2) MLB capture is fail-closed against MLB StatsAPI status/first-play rather than
   provider commence_time alone.

Still NOT_EVIDENCE and carries no promotion authority.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import scripts.capture_closing_line_archive as v1

UTC = timezone.utc
WINDOW_PRIORITY = ("close", "t0_prestart", "decision")


def _norm_team(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def prioritized_window_for(start: datetime, now: datetime, policy: Mapping[str, Any]) -> str | None:
    lead = (start - now).total_seconds() / 60.0
    if lead <= 0:
        return None
    windows = policy["windows"]
    for name in WINDOW_PRIORITY:
        if name not in windows:
            continue
        bounds = windows[name]
        if bounds["min_minutes_before_start"] <= lead <= bounds["max_minutes_before_start"]:
            return name
    for name, bounds in windows.items():
        if name in WINDOW_PRIORITY:
            continue
        if bounds["min_minutes_before_start"] <= lead <= bounds["max_minutes_before_start"]:
            return name
    return None


def due_events(events, now: datetime, policy: Mapping[str, Any]) -> dict[str, str]:
    due: dict[str, str] = {}
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        try:
            start = v1._parse_ts(event.get("commence_time"))
        except v1.ArchiveError:
            continue
        name = prioritized_window_for(start, now, policy)
        if name:
            due[event_id] = name
    return due


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "SportsEdge-closing-line-archive/2"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _mlb_match(event: Mapping[str, Any], start: datetime) -> tuple[int, dict[str, Any]] | None:
    home = _norm_team(event.get("home_team"))
    away = _norm_team(event.get("away_team"))
    if not home or not away:
        return None
    matches: dict[int, dict[str, Any]] = {}
    for delta in (-1, 0, 1):
        date_text = (start + timedelta(days=delta)).date().isoformat()
        url = "https://statsapi.mlb.com/api/v1/schedule?" + urllib.parse.urlencode({"sportId": 1, "date": date_text})
        payload = _get_json(url)
        for date_row in payload.get("dates", []) or []:
            for game in date_row.get("games", []) or []:
                mh = _norm_team((((game.get("teams") or {}).get("home") or {}).get("team") or {}).get("name"))
                ma = _norm_team((((game.get("teams") or {}).get("away") or {}).get("team") or {}).get("name"))
                if {home, away} == {mh, ma}:
                    matches[int(game["gamePk"])] = game
    if len(matches) != 1:
        return None
    return next(iter(matches.items()))


def mlb_actual_start_guard(event: Mapping[str, Any]) -> dict[str, Any]:
    try:
        start = v1._parse_ts(event.get("commence_time"))
        matched = _mlb_match(event, start)
        if matched is None:
            return {"known": False, "started": None, "reason": "MLB_STATSAPI_EVENT_IDENTITY_UNRESOLVED"}
        game_pk, schedule_game = matched
        feed = _get_json(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
        schedule_state = str(((schedule_game.get("status") or {}).get("abstractGameState") or "")).strip()
        feed_state = str((((feed.get("gameData") or {}).get("status") or {}).get("abstractGameState") or "")).strip()
        plays = (((feed.get("liveData") or {}).get("plays") or {}).get("allPlays") or [])
        first_play = None
        if plays:
            first_play = ((plays[0].get("about") or {}).get("startTime"))
        started = bool(plays) or schedule_state in {"Live", "Final"} or feed_state in {"Live", "Final"}
        return {
            "known": True,
            "started": started,
            "reason": "MLB_ALREADY_STARTED" if started else "MLB_CONFIRMED_PRESTART",
            "game_pk": str(game_pk),
            "schedule_state": schedule_state,
            "feed_state": feed_state,
            "actual_first_play_utc": first_play,
        }
    except Exception as exc:
        return {"known": False, "started": None, "reason": f"MLB_STATSAPI_GUARD_ERROR:{type(exc).__name__}"}


def run(*, now: datetime, policy: Mapping[str, Any], out_dir: Path, keys: list[str], opener, dry_run: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {
        "policy_id": policy["policy_id"],
        "archive_guard_version": "ACTUAL_START_GUARD_V2",
        "evidence_class": "NOT_EVIDENCE",
        "ran_at": v1._iso(now),
        "dry_run": dry_run,
        "sports": {},
    }
    for label, sport_key in policy["sports"].items():
        events = v1.fetch_event_index(sport_key, keys, opener)
        due = due_events(events, now, policy)
        skipped_guard: list[dict[str, Any]] = []
        if label == "MLB" and due:
            by_id = {str(e.get("id") or ""): e for e in events}
            guarded: dict[str, str] = {}
            for event_id, window in due.items():
                guard = mlb_actual_start_guard(by_id[event_id])
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
            rows, skipped = v1.build_rows(sport_key, odds_payload, due, now, policy)
            written = v1.append_rows(rows, out_dir, policy)
            entry["rows_written"] = sum(written.values())
            entry["files"] = written
            entry["skipped"].extend(skipped)
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
        report = run(now=now, policy=policy, out_dir=Path(args.out_dir), keys=v1.api_keys(), opener=v1._default_opener, dry_run=args.dry_run)
    except v1.ArchiveError as exc:
        failure = {"state": "BLOCKED", "reason": str(exc)}
        text = json.dumps(failure, indent=2)
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
