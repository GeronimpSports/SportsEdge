#!/usr/bin/env python3
"""Record elapsed NFL confirmation windows that have no genuine capture.

This script never fetches odds and never creates a substitute capture. It only
writes immutable MISSED_OR_BLOCKED evidence after a frozen capture window has
fully elapsed and the expected capture file is absent.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def week_for_tuesday(tuesday: date, cfg: dict) -> int:
    anchor = date.fromisoformat(cfg["week1_tuesday_local_date"])
    return (tuesday - anchor).days // 7 + 1


def opener_window_for_week(week: int, cfg: dict):
    anchor = date.fromisoformat(cfg["week1_tuesday_local_date"])
    target_day = anchor + timedelta(days=7 * (week - 1))
    target_weekday = cfg["opener_weekday"]
    weekday_num = {"Sunday": 6, "Monday": 0, "Tuesday": 1}[target_weekday]
    target_day += timedelta(days=(weekday_num - target_day.weekday()) % 7)
    hh, mm = map(int, cfg["opener_local_time"].split(":"))
    tz = ZoneInfo(cfg["timezone"])
    start = datetime(target_day.year, target_day.month, target_day.day, hh, mm, tzinfo=tz)
    end = start + timedelta(minutes=int(cfg["opener_window_minutes"]))
    return start, end


def audit(cfg: dict, now: datetime) -> list[Path]:
    out_dir = Path(cfg["output_dir"])
    tz = ZoneInfo(cfg["timezone"])
    local_now = now.astimezone(tz)
    anchor = date.fromisoformat(cfg["week1_tuesday_local_date"])
    current_week = max(1, (local_now.date() - anchor).days // 7 + 1)
    written: list[Path] = []

    for week in range(int(cfg["first_week"]), current_week + 1):
        start, end = opener_window_for_week(week, cfg)
        if local_now < end:
            continue
        week_dir = out_dir / f"week{week:02d}"
        opener = week_dir / "opener.json"
        marker = week_dir / "opener_missed.json"
        if opener.exists() or marker.exists():
            continue
        week_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "status": "MISSED_OR_BLOCKED",
            "capture_kind": "OPENER",
            "week": week,
            "reason": "OPENER_WINDOW_ELAPSED_WITHOUT_CAPTURE",
            "target_local": start.isoformat(),
            "window_end_local": end.isoformat(),
            "observed_missing_at_utc": now.astimezone(timezone.utc).isoformat(),
            "expected_capture_path": str(opener),
            "no_backfill": True,
            "evidence_semantics": "ABSENCE_MARKER_ONLY_NOT_MARKET_DATA",
        }
        marker.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(marker)
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/nfl_2026_capture.json")
    parser.add_argument("--now", help="ISO timestamp override for deterministic tests/audits")
    args = parser.parse_args()
    cfg = load_json(Path(args.config))
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SystemExit("NFL_CAPTURE_GAP_AUDIT_NOW_MUST_BE_TIMEZONE_AWARE")
    written = audit(cfg, now)
    print(json.dumps({"status": "PASS", "markers_written": [str(p) for p in written]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
