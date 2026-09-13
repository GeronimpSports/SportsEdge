#!/usr/bin/env python3
"""Archive raw MLB schedule/boxscore observations for future PIT replay.

This collector creates source evidence only. It does not create Model_P, validation
PASS, eligibility, a Truth Gate floor, or OFFICIAL status.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://statsapi.mlb.com"
DEFAULT_ROOT = Path("artifacts/mlb_pit_inputs")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _ts(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _fetch(url: str, opener=urlopen) -> bytes:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "SportsEdge-MLB-PIT-Inputs/1.0"})
    with opener(req, timeout=20) as response:
        return response.read()


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)


def _json(path: Path, value: Any) -> None:
    _atomic(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _blob(root: Path, kind: str, raw: bytes) -> tuple[str, Path]:
    digest = _sha(raw)
    path = root / "raw" / kind / f"{digest}.json"
    if not path.exists():
        _atomic(path, raw)
    elif _sha(path.read_bytes()) != digest:
        raise RuntimeError(f"RAW_BLOB_HASH_MISMATCH:{path}")
    return digest, path


def _parse_schedule(raw: bytes) -> list[dict[str, Any]]:
    payload = json.loads(raw.decode("utf-8"))
    games: list[dict[str, Any]] = []
    for block in payload.get("dates", []):
        for game in block.get("games", []):
            teams = game.get("teams") or {}
            away = teams.get("away") or {}
            home = teams.get("home") or {}
            away_team = away.get("team") or {}
            home_team = home.get("team") or {}
            game_pk = game.get("gamePk")
            if game_pk in (None, "") or away_team.get("id") in (None, "") or home_team.get("id") in (None, ""):
                continue
            games.append({
                "game_pk": int(game_pk),
                "game_date": game.get("gameDate"),
                "status": (game.get("status") or {}).get("abstractGameState"),
                "away_team_id": int(away_team["id"]),
                "home_team_id": int(home_team["id"]),
                "away_probable_pitcher_id": (away.get("probablePitcher") or {}).get("id"),
                "home_probable_pitcher_id": (home.get("probablePitcher") or {}).get("id"),
            })
    return games


def _lineup_ids(box: dict[str, Any], side: str) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    players = (((box.get("teams") or {}).get(side) or {}).get("players") or {})
    for row in players.values():
        order = row.get("battingOrder")
        pid = (row.get("person") or {}).get("id")
        if order in (None, "") or pid in (None, ""):
            continue
        code = int(order)
        if code <= 0:
            continue
        slot, sequence = divmod(code, 100)
        out.append({"player_id": int(pid), "slot": slot, "sequence": sequence})
    out.sort(key=lambda x: (x["slot"], x["sequence"], x["player_id"]))
    return out


def capture(slate_date: str, *, root: Path = DEFAULT_ROOT, now: datetime | None = None, opener=urlopen) -> dict[str, Any]:
    observed = now or datetime.now(timezone.utc)
    observed_at = _ts(observed)
    stamp = observed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    schedule_url = BASE + "/api/v1/schedule?" + urlencode({"sportId": 1, "date": slate_date, "hydrate": "probablePitcher,team"})
    schedule_raw = _fetch(schedule_url, opener=opener)
    schedule_sha, schedule_blob = _blob(root, "schedule", schedule_raw)
    games = _parse_schedule(schedule_raw)
    observations: list[dict[str, Any]] = []
    for game in games:
        game_pk = int(game["game_pk"])
        box_url = f"{BASE}/api/v1/game/{game_pk}/boxscore"
        box_raw = _fetch(box_url, opener=opener)
        box_sha, box_blob = _blob(root, "boxscore", box_raw)
        box = json.loads(box_raw.decode("utf-8"))
        away_lineup = _lineup_ids(box, "away")
        home_lineup = _lineup_ids(box, "home")
        observation = {
            "schema": "SPORTSEDGE_MLB_PIT_LINEUP_STARTER_OBSERVATION_V1",
            "observed_at_utc": observed_at,
            "slate_date": slate_date,
            "game_pk": game_pk,
            "scheduled_start_utc": game.get("game_date"),
            "game_status": game.get("status"),
            "away_team_id": game["away_team_id"],
            "home_team_id": game["home_team_id"],
            "away_probable_pitcher_id": game.get("away_probable_pitcher_id"),
            "home_probable_pitcher_id": game.get("home_probable_pitcher_id"),
            "away_lineup": away_lineup,
            "home_lineup": home_lineup,
            "away_lineup_primary_slots": sorted({x["slot"] for x in away_lineup if x["sequence"] == 0}),
            "home_lineup_primary_slots": sorted({x["slot"] for x in home_lineup if x["sequence"] == 0}),
            "schedule_source_sha256": schedule_sha,
            "boxscore_source_sha256": box_sha,
            "schedule_blob": schedule_blob.as_posix(),
            "boxscore_blob": box_blob.as_posix(),
            "retroactive_point_in_time_claim": False,
            "promotion_authority": False,
            "model_p_authority": False,
        }
        path = root / "observations" / slate_date / str(game_pk) / f"{stamp}.json"
        _json(path, observation)
        observations.append({"game_pk": game_pk, "path": path.as_posix(), "boxscore_source_sha256": box_sha})
    summary = {
        "schema": "SPORTSEDGE_MLB_PIT_LINEUP_STARTER_CAPTURE_V1",
        "observed_at_utc": observed_at,
        "slate_date": slate_date,
        "schedule_source_sha256": schedule_sha,
        "games_observed": len(observations),
        "observations": observations,
        "promotion_authority": False,
    }
    _json(root / "runs" / slate_date / f"{stamp}.json", summary)
    return summary


def self_test() -> int:
    fixture = {"dates": [{"games": [{"gamePk": 1, "gameDate": "2026-09-12T23:00:00Z", "status": {"abstractGameState": "Preview"}, "teams": {"away": {"team": {"id": 10}, "probablePitcher": {"id": 101}}, "home": {"team": {"id": 20}, "probablePitcher": {"id": 202}}}}]}]}
    rows = _parse_schedule(json.dumps(fixture).encode())
    assert rows[0]["away_probable_pitcher_id"] == 101 and rows[0]["home_probable_pitcher_id"] == 202
    box = {"teams": {"away": {"players": {"a": {"person": {"id": 7}, "battingOrder": "100"}}}}}
    assert _lineup_ids(box, "away") == [{"player_id": 7, "slot": 1, "sequence": 0}]
    print(json.dumps({"status": "SELF_TEST_OK", "promotion_authority": False, "raw_blob_sha256_bound": True}))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    print(json.dumps(capture(args.date, root=args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
