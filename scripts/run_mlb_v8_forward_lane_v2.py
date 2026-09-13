#!/usr/bin/env python3
"""V2 MLB forward lane with same-fetch lineup/starter PIT source binding.

Planning semantics are imported unchanged from V1. Decision evidence is persisted
only after the exact StatsAPI schedule and boxscore bytes consumed by the model are
bound into source_provenance. Missing, ambiguous, late, or hash-mismatched source
records fail closed. Existing V1 evidence is never rewritten or backfilled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from run_mlb_v8_forward_lane import (
    CT,
    DECISION_TARGET_MIN,
    DECISION_TOLERANCE_DIRECTION,
    DECISION_TOLERANCE_MIN,
    _canonical_sha,
    _decision_rows,
    _now,
    _parse_ts,
    _quote_rows,
    build_plan,
    fetch_schedule,
)
from capture_mlb_v8_forward_evidence import persist
from sportsedge.mlb_pit_binding import MLBPITBindingError, bind_v8_game_sources


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _validate_decision_rows(rows: list[dict]) -> None:
    for row in rows:
        if not _valid_sha256(row.get("model_input_hash")):
            raise RuntimeError("V8 decision row model_input_hash must be sha256")
        if not _valid_sha256(row.get("distribution_sha256")):
            raise RuntimeError("V8 decision row distribution_sha256 must be sha256")
        readout = row.get("readout_sha256")
        if readout not in (None, "") and not _valid_sha256(readout):
            raise RuntimeError("V8 decision row readout_sha256 must be sha256 when present")


def materialize(
    *,
    plan: dict,
    card_raw: bytes,
    model_sha: str,
    run_id: str,
    captured_at: datetime | None = None,
    root: Path | None = None,
) -> list[Path]:
    card = json.loads(card_raw.decode("utf-8"))
    results = card.get("results")
    if not isinstance(results, list):
        raise RuntimeError("canonical MLB card results missing")
    if not plan.get("needs_model"):
        return []
    current = _parse_ts((captured_at or _now()).isoformat())
    card_sha = _sha(card_raw)
    written: list[Path] = []

    for game in plan.get("games") or []:
        phases = list(game.get("phases") or [])
        if not phases:
            continue
        game_id = str(game["game_id"])
        quotes = _quote_rows(results, game_id)
        if not quotes:
            raise RuntimeError(f"V8 target game has no canonical sportsbook quotes:{game_id}")
        first_pitch = _parse_ts(game["first_pitch_at"])
        if current >= first_pitch:
            raise RuntimeError(f"V8 target game passed first pitch before evidence write:{game_id}")
        actual_minutes = (first_pitch - current).total_seconds() / 60.0
        base_provenance = {
            "provider": "SPORTSEDGE_CANONICAL_MLB_MACHINE",
            "card_sha256": card_sha,
            "card_generated_at_utc": card.get("generated_at_utc"),
            "machine_mode": card.get("mode"),
            "run_status": card.get("run_status"),
            "runner": "scripts/run_auto_mlb_resilient.py",
            "model_release_identity": "EXACT_GIT_COMMIT_SHA",
            "model_release_sha": model_sha,
            "books": sorted({str(q["book_key"]) for q in quotes}),
        }
        common = {
            "game_id": game_id,
            "first_pitch_at": first_pitch.isoformat(),
            "captured_at": current.isoformat(),
            "minutes_before_first_pitch": round(actual_minutes, 3),
            "quotes": quotes,
            "source_provenance": base_provenance,
            "capture_labels": list(game.get("capture_labels") or []),
            "slate_date_ct": plan.get("slate_date_ct"),
        }
        for phase in phases:
            payload = dict(common)
            if phase == "decision":
                timing_ok = (
                    actual_minutes >= DECISION_TARGET_MIN
                    and (actual_minutes - DECISION_TARGET_MIN) <= DECISION_TOLERANCE_MIN
                )
                if not timing_ok:
                    raise RuntimeError(
                        f"V8 decision write attempted outside one-sided T-30 window:{game_id}:{actual_minutes:.3f}"
                    )
                decisions = _decision_rows(results, game_id)
                if not decisions:
                    raise RuntimeError(f"V8 decision target has no model/distribution evidence:{game_id}")
                _validate_decision_rows(decisions)

                # Critical ordering: bind raw source bytes before persist() hashes the
                # decision payload. No evidence record is mutated after persistence.
                decision_provenance = dict(base_provenance)
                decision_provenance.update(
                    bind_v8_game_sources(card, game_id=game_id, captured_at=current)
                )
                payload["source_provenance"] = decision_provenance
                dist_binding = [
                    {
                        "source_index": row.get("source_index"),
                        "market": row.get("market"),
                        "entity_id": row.get("entity_id"),
                        "distribution_sha256": row.get("distribution_sha256"),
                    }
                    for row in decisions
                ]
                payload.update({
                    "run_id": run_id,
                    "model_sha": model_sha,
                    "distribution_sha": _canonical_sha(dist_binding),
                    "decision_rows": decisions,
                    "decision_target_minutes": DECISION_TARGET_MIN,
                    "decision_target_qualified": True,
                    "decision_tolerance_direction": DECISION_TOLERANCE_DIRECTION,
                })
            written.append(persist(payload, phase, root=root or Path("artifacts/mlb_v8_forward")))
    return written


def _raw_sources(root: Path, *, game_pk: int, observed_at: str) -> dict:
    schedule_payload = {
        "dates": [{
            "date": "2026-09-03",
            "games": [{
                "gamePk": game_pk,
                "gameDate": "2026-09-03T23:00:00Z",
                "status": {"abstractGameState": "Preview"},
                "teams": {
                    "away": {"team": {"id": 1, "name": "Away"}, "probablePitcher": {"id": 101}},
                    "home": {"team": {"id": 2, "name": "Home"}, "probablePitcher": {"id": 202}},
                },
            }],
        }],
    }
    boxscore_payload = {
        "teams": {
            "away": {"players": {"ID11": {"person": {"id": 11}, "battingOrder": "100"}}},
            "home": {"players": {"ID22": {"person": {"id": 22}, "battingOrder": "100"}}},
        },
    }
    schedule_raw = (json.dumps(schedule_payload, separators=(", ", ": ")) + "\n").encode()
    boxscore_raw = ("  " + json.dumps(boxscore_payload, separators=(",", ":")) + "\n").encode()
    schedule_path = root / "schedule.json"
    boxscore_path = root / f"game_{game_pk}_boxscore.json"
    schedule_path.write_bytes(schedule_raw)
    boxscore_path.write_bytes(boxscore_raw)
    return {
        "schema": "MLB_SAME_FETCH_PIT_SOURCE_CAPTURE_V1",
        "capture_semantics": "SAME_RESPONSE_BYTES_CONSUMED_BY_MODEL",
        "promotion_authority": False,
        "retroactive_point_in_time_claim": False,
        "records": [
            {
                "sequence": 1,
                "source_kind": "MLB_STATSAPI_SCHEDULE",
                "url": "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-09-03&hydrate=probablePitcher,team",
                "observed_at_utc": observed_at,
                "sha256": _sha(schedule_raw),
                "path": str(schedule_path),
                "byte_length": len(schedule_raw),
                "game_pk": None,
            },
            {
                "sequence": 2,
                "source_kind": "MLB_STATSAPI_BOXSCORE",
                "url": f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore",
                "observed_at_utc": observed_at,
                "sha256": _sha(boxscore_raw),
                "path": str(boxscore_path),
                "byte_length": len(boxscore_raw),
                "game_pk": game_pk,
            },
        ],
    }


def self_test() -> int:
    now = datetime(2026, 9, 3, 22, 30, tzinfo=timezone.utc)
    games = [{
        "game_id": "123",
        "first_pitch_at": "2026-09-03T23:00:00+00:00",
        "abstract_game_state": "Preview",
        "home_team": "Home",
        "away_team": "Away",
    }]
    plan = build_plan(now, games)
    assert plan["needs_model"] is True
    assert plan["games"][0]["decision_target_qualified"] is True

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = _raw_sources(root, game_pk=123, observed_at="2026-09-03T22:29:50+00:00")
        card = {
            "mode": "AUTOMATIC",
            "generated_at_utc": now.isoformat(),
            "run_status": "PASS",
            "pit_source_capture": manifest,
            "results": [{
                "source_index": 1,
                "game_id": "123",
                "market": "MONEYLINE",
                "entity_id": "2",
                "line": None,
                "side": "HOME",
                "american_odds": -120,
                "model_p": 0.56,
                "implied_probability": 0.545,
                "edge": 0.015,
                "ev_per_dollar": 0.02,
                "bet_status": "MODEL_CANDIDATE",
                "reason": "DEPLOYMENT_NOT_ELIGIBLE",
                "model_input_hash": "1" * 64,
                "distribution_sha256": "d" * 64,
                "readout_sha256": "e" * 64,
                "readout_version": "v",
                "engine_version": "v8",
                "seed_policy": "identity_sha256_256bit",
                "mc_paths": 100000,
                "book_key": "draftkings",
                "sportsbook": "DraftKings",
                "quote_retrieved_at": "2026-09-03T22:29:40+00:00",
                "offer_id": "offer-1",
            }],
        }
        raw = (json.dumps(card, sort_keys=True) + "\n").encode()
        evidence_root = root / "evidence"
        paths = materialize(
            plan=plan,
            card_raw=raw,
            model_sha="a" * 40,
            run_id="run-1",
            captured_at=now,
            root=evidence_root,
        )
        assert len(paths) == 1
        record = json.loads(paths[0].read_text())
        provenance = record["payload"]["source_provenance"]
        assert provenance["pit_capture_semantics"] == "SAME_RESPONSE_BYTES_CONSUMED_BY_MODEL"
        assert provenance["starter_snapshot_sha256"] == manifest["records"][0]["sha256"]
        assert provenance["lineup_snapshot_sha256"] == manifest["records"][1]["sha256"]
        assert provenance["pit_binding_promotion_authority"] is False
        assert provenance["pit_binding_retroactive_claim"] is False

        missing = dict(card)
        missing.pop("pit_source_capture")
        try:
            materialize(
                plan=plan,
                card_raw=(json.dumps(missing, sort_keys=True) + "\n").encode(),
                model_sha="a" * 40,
                run_id="run-2",
                captured_at=now,
                root=root / "blocked",
            )
        except MLBPITBindingError:
            pass
        else:
            raise AssertionError("decision evidence persisted without same-fetch PIT source manifest")

        ambiguous = json.loads(json.dumps(card))
        ambiguous["pit_source_capture"]["records"].append(dict(manifest["records"][0]))
        try:
            materialize(
                plan=plan,
                card_raw=(json.dumps(ambiguous, sort_keys=True) + "\n").encode(),
                model_sha="a" * 40,
                run_id="run-3",
                captured_at=now,
                root=root / "ambiguous",
            )
        except MLBPITBindingError:
            pass
        else:
            raise AssertionError("ambiguous same-fetch schedule sources were accepted")

    print(json.dumps({
        "status": "SELF_TEST_OK",
        "same_fetch_binding": True,
        "missing_manifest_blocked": True,
        "ambiguous_sources_blocked": True,
        "promotion_authority": False,
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--card", type=Path)
    parser.add_argument("--model-sha")
    parser.add_argument("--run-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.plan_output:
        now = _now()
        slate = now.astimezone(CT).date().isoformat()
        plan = build_plan(now, fetch_schedule(slate))
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        print(json.dumps(plan, sort_keys=True))
        return 0
    if not all((args.plan, args.card, args.model_sha, args.run_id)):
        parser.error("materialization requires --plan --card --model-sha --run-id")
    written = materialize(
        plan=json.loads(args.plan.read_text()),
        card_raw=args.card.read_bytes(),
        model_sha=str(args.model_sha),
        run_id=str(args.run_id),
    )
    print(json.dumps({
        "status": "V8_FORWARD_CAPTURE_COMPLETE_V2",
        "records_written": len(written),
        "paths": [str(path) for path in written],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
