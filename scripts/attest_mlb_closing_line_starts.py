"""Append-only MLB actual-start attestations for closing-line archive rows.

Uses MLB StatsAPI only to establish actual first-play time. This lane is
adjudication metadata only: NOT_EVIDENCE and no promotion authority.
"""
from __future__ import annotations

import argparse, hashlib, json, urllib.request
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

UTC = timezone.utc
SPORT_KEY = "baseball_mlb"
SCHEMA = "CLOSING_LINE_START_ATTESTATION_V1"


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def _archive_events(root: Path, lookback_days: int) -> dict[str, dict]:
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    out = {}
    base = root / "archive/closing-lines" / SPORT_KEY
    if not base.exists():
        return out
    for p in base.glob("*.ndjson"):
        for line in p.read_text().splitlines():
            row = json.loads(line)
            if _parse(row["commence_time"]) < cutoff:
                continue
            out.setdefault(row["event_id"], row)
    return out


def _existing(root: Path) -> dict[str, dict]:
    out = {}
    base = root / "archive/closing-line-start-attestations" / SPORT_KEY
    if not base.exists():
        return out
    for p in base.glob("*.ndjson"):
        for line in p.read_text().splitlines():
            row = json.loads(line)
            out[row["event_id"]] = row
    return out


@lru_cache(maxsize=16)
def _schedule(date: str) -> list[dict]:
    raw = _get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}")
    payload = json.loads(raw)
    return [g for d in payload.get("dates", []) for g in d.get("games", [])]


def _match_game(row: dict) -> int | None:
    base = _parse(row["commence_time"])
    candidates = []
    for delta in (-1, 0, 1):
        for g in _schedule((base + timedelta(days=delta)).date().isoformat()):
            home = g.get("teams", {}).get("home", {}).get("team", {}).get("name")
            away = g.get("teams", {}).get("away", {}).get("team", {}).get("name")
            if home == row.get("home_team") and away == row.get("away_team"):
                candidates.append(int(g["gamePk"]))
    uniq = sorted(set(candidates))
    return uniq[0] if len(uniq) == 1 else None


def _attest(event_id: str, row: dict, game_pk: int) -> dict | None:
    raw = _get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    feed = json.loads(raw)
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not plays:
        return None
    start = plays[0].get("about", {}).get("startTime")
    if not start:
        return None
    return {
        "schema_version": SCHEMA,
        "evidence_class": "NOT_EVIDENCE_ADJUDICATION_ONLY",
        "promotion_authority": False,
        "sport_key": SPORT_KEY,
        "event_id": event_id,
        "actual_first_play_utc": _iso(_parse(start)),
        "observed_at_utc": _iso(datetime.now(UTC)),
        "source": "MLB_STATSAPI_GAME_FEED",
        "source_event_id": str(game_pk),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "identity_method": "EXACT_HOME_AWAY_UNIQUE_WITHIN_DATE_PLUS_MINUS_1",
        "retroactive_point_in_time_claim": False
    }


def run(root: Path, lookback_days: int = 3) -> dict:
    _schedule.cache_clear()
    events, existing = _archive_events(root, lookback_days), _existing(root)
    written = blocked = 0
    for event_id, row in events.items():
        if event_id in existing:
            continue
        game_pk = _match_game(row)
        if game_pk is None:
            blocked += 1
            continue
        att = _attest(event_id, row, game_pk)
        if att is None:
            continue
        date = att["actual_first_play_utc"][:10]
        target = root / "archive/closing-line-start-attestations" / SPORT_KEY / f"{date}.ndjson"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as f:
            f.write(json.dumps(att, sort_keys=True) + "\n")
        written += 1
    return {"status": "OK", "events_seen": len(events), "attestations_written": written, "identity_blocked": blocked, "promotion_authority": False}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default=".")
    p.add_argument("--lookback-days", type=int, default=3)
    args = p.parse_args(argv)
    print(json.dumps(run(Path(args.data_root), args.lookback_days), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
