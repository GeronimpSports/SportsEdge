#!/usr/bin/env python3
"""Acquire immutable actual-first-play attestations for MLB V8 historical fixtures.

This is adjudication/provenance metadata only. It never creates Model_P,
market eligibility, Truth Gate authority, or a retroactive PIT feature claim.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen

UTC = timezone.utc
DEFAULT_ROOT = Path("artifacts/mlb_v8_replay_sources/ODDSPAPI_HISTORICAL")
SOURCE = "MLB_STATSAPI_GAME_FEED"
SCHEMA = "MLB_V8_ACTUAL_FIRST_PLAY_ATTESTATION_V1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return dt.astimezone(UTC)


def _get(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        return response.read()


def _norm_team(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _schedule(date_text: str, cache: dict[str, tuple[bytes, list[dict]]]) -> tuple[bytes, list[dict]]:
    if date_text not in cache:
        raw = _get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_text}")
        payload = json.loads(raw)
        games = [g for d in payload.get("dates", []) for g in d.get("games", [])]
        cache[date_text] = (raw, games)
    return cache[date_text]


def _match_fixture(fixture: dict, cache: dict[str, tuple[bytes, list[dict]]]):
    scheduled = _parse(fixture["startTime"])
    home = _norm_team(fixture.get("participant1Name"))
    away = _norm_team(fixture.get("participant2Name"))
    matches: list[tuple[int, bytes]] = []
    # Odds providers do not always encode home/away in participant1/2 order, so
    # require an exact unordered team-pair identity and uniqueness across +/-1 day.
    for delta in (-1, 0, 1):
        date_text = (scheduled + timedelta(days=delta)).date().isoformat()
        schedule_raw, games = _schedule(date_text, cache)
        for game in games:
            mlb_home = _norm_team(game.get("teams", {}).get("home", {}).get("team", {}).get("name"))
            mlb_away = _norm_team(game.get("teams", {}).get("away", {}).get("team", {}).get("name"))
            if {home, away} == {mlb_home, mlb_away} and home and away:
                matches.append((int(game["gamePk"]), schedule_raw))
    unique = {game_pk: raw for game_pk, raw in matches}
    if len(unique) != 1:
        return None
    return next(iter(unique.items()))


def _attest(fixture_path: Path, fixture: dict, game_pk: int, schedule_raw: bytes) -> dict | None:
    feed_raw = _get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")
    feed = json.loads(feed_raw)
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
    if not plays:
        return None
    first_play = plays[0].get("about", {}).get("startTime")
    if not first_play:
        return None
    fixture_raw = fixture_path.read_bytes()
    return {
        "schema": SCHEMA,
        "evidence_class": "NOT_EVIDENCE_ADJUDICATION_ONLY",
        "promotion_authority": False,
        "retroactive_point_in_time_claim": False,
        "fixture_id": str(fixture.get("fixtureId")),
        "provider_scheduled_start_utc": _parse(fixture["startTime"]).isoformat(),
        "actual_first_play_utc": _parse(first_play).isoformat(),
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "source": SOURCE,
        "source_event_id": str(game_pk),
        "identity_method": "UNIQUE_EXACT_NORMALIZED_TEAM_PAIR_WITHIN_DATE_PLUS_MINUS_1",
        "fixture_sha256": _sha(fixture_raw),
        "schedule_payload_sha256": _sha(schedule_raw),
        "game_feed_payload_sha256": _sha(feed_raw),
    }


def run(root: Path) -> dict:
    out_dir = root / "actual_starts"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache: dict[str, tuple[bytes, list[dict]]] = {}
    written = existing = identity_blocked = no_first_play = 0
    for fixture_path in sorted(root.glob("????-??-??/*/fixture.normalized.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_id = str(fixture.get("fixtureId") or "").strip()
        if not fixture_id:
            identity_blocked += 1
            continue
        target = out_dir / f"{fixture_id}.json"
        if target.exists():
            existing += 1
            continue
        matched = _match_fixture(fixture, cache)
        if matched is None:
            identity_blocked += 1
            continue
        att = _attest(fixture_path, fixture, matched[0], matched[1])
        if att is None:
            no_first_play += 1
            continue
        target.write_text(json.dumps(att, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written += 1
    return {
        "status": "OK",
        "attestations_written": written,
        "already_attested": existing,
        "identity_blocked": identity_blocked,
        "no_first_play": no_first_play,
        "promotion_authority": False,
    }


def self_test() -> int:
    assert _norm_team("St. Louis Cardinals") == "stlouiscardinals"
    assert _norm_team("Kansas City Royals") == "kansascityroyals"
    assert _parse("2026-06-05T19:10:00Z").tzinfo is not None
    print(json.dumps({"status": "SELF_TEST_OK", "promotion_authority": False}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    print(json.dumps(run(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
