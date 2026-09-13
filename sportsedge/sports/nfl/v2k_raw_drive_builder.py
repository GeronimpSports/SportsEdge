"""Deterministic nflfastR PBP -> V2K source-normalized drive rows.

Research only. This module deliberately has no dependency on the V2K fit,
simulator, evaluator, market-pricing, or RUN IT stack. It only normalizes the
already-preregistered drive identity, start field position, and terminal outcome.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable, Mapping

SCHEMA = "SPORTSEDGE_NFL_V2K_RAW_DRIVE_NORMALIZATION_V1"


@dataclass(frozen=True)
class NormalizedDriveRow:
    game_id: str
    drive_id: str
    kickoff_utc: str
    offense: str
    defense: str
    start_yard: float
    outcome: str


FIXED_RESULT_TO_V2K = {
    "Touchdown": "TD",
    "Field goal": "FG",
    "Turnover": "TURNOVER",
    "Turnover on downs": "TURNOVER",
    "Punt": "PUNT_OTHER",
    "Missed field goal": "PUNT_OTHER",
    "End of half": "PUNT_OTHER",
    "Safety": "SAFETY",
    "Opp touchdown": "DEF_ST_TD",
}

NON_SCRIMMAGE_START_TYPES = frozenset({
    "kickoff",
    "extra_point",
    "two_point_attempt",
})


def _aware(value: str) -> str:
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        raise ValueError("kickoff_utc required")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff_utc must be timezone-aware")
    return parsed.isoformat()


def _drive_id(value: object) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError("fixed_drive required")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("fixed_drive must be numeric") from exc
    if not isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError("fixed_drive must be a positive integer")
    return str(int(number))


def _play_id(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("play_id required and numeric") from exc
    if not isfinite(out):
        raise ValueError("play_id required and numeric")
    return out


def normalize_start_yard(yardline_100: object) -> float:
    """Convert nflfastR yards-to-opponent-endzone to own-goal-line coordinate."""
    try:
        y100 = float(yardline_100)
    except (TypeError, ValueError) as exc:
        raise ValueError("yardline_100 required and numeric") from exc
    if not isfinite(y100) or not 1.0 <= y100 <= 99.0:
        raise ValueError("yardline_100 outside normalization range 1..99")
    start = 100.0 - y100
    if not 1.0 <= start <= 99.0:
        raise ValueError("normalized start_yard outside 1..99")
    return start


def normalize_fixed_drive_result(raw: object) -> str:
    value = str(raw or "").strip()
    if value not in FIXED_RESULT_TO_V2K:
        raise ValueError(f"NFL_V2K_FIXED_DRIVE_RESULT_UNMAPPED:{value or 'EMPTY'}")
    return FIXED_RESULT_TO_V2K[value]


def build_drive_rows(
    pbp_rows: Iterable[Mapping[str, object]],
    *,
    kickoff_by_game: Mapping[str, str],
) -> list[NormalizedDriveRow]:
    """Build one deterministic source-normalized row per nflfastR fixed drive."""
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for raw in pbp_rows:
        if not isinstance(raw, Mapping):
            raise ValueError("PBP row must be a mapping")
        if raw.get("fixed_drive") is None:
            continue
        game_id = str(raw.get("game_id") or "").strip()
        if not game_id:
            raise ValueError("game_id required when fixed_drive is present")
        drive_id = _drive_id(raw.get("fixed_drive"))
        row = dict(raw)
        row["__play_id"] = _play_id(raw.get("play_id"))
        grouped[(game_id, drive_id)].append(row)

    if not grouped:
        raise ValueError("NFL_V2K_NO_FIXED_DRIVES")

    out: list[NormalizedDriveRow] = []
    for (game_id, drive_id), rows in grouped.items():
        if game_id not in kickoff_by_game:
            raise ValueError(f"NFL_V2K_KICKOFF_MISSING:{game_id}")
        kickoff = _aware(kickoff_by_game[game_id])

        results = {str(r.get("fixed_drive_result") or "").strip() for r in rows}
        results.discard("")
        if len(results) != 1:
            raise ValueError(f"NFL_V2K_DRIVE_RESULT_AMBIGUOUS:{game_id}:{drive_id}")
        outcome = normalize_fixed_drive_result(next(iter(results)))

        pairs = {
            (str(r.get("posteam") or "").strip(), str(r.get("defteam") or "").strip())
            for r in rows
            if str(r.get("posteam") or "").strip() and str(r.get("defteam") or "").strip()
        }
        if len(pairs) != 1:
            raise ValueError(f"NFL_V2K_DRIVE_IDENTITY_AMBIGUOUS:{game_id}:{drive_id}")
        offense, defense = next(iter(pairs))
        if offense == defense:
            raise ValueError(f"NFL_V2K_DRIVE_IDENTITY_INVALID:{game_id}:{drive_id}")

        candidates: list[tuple[float, float]] = []
        for r in rows:
            if str(r.get("posteam") or "").strip() != offense:
                continue
            if str(r.get("defteam") or "").strip() != defense:
                continue
            play_type = str(r.get("play_type") or "").strip().lower()
            if play_type in NON_SCRIMMAGE_START_TYPES:
                continue
            if r.get("yardline_100") is None:
                continue
            try:
                start_yard = normalize_start_yard(r.get("yardline_100"))
            except ValueError:
                continue
            candidates.append((float(r["__play_id"]), start_yard))
        if not candidates:
            raise ValueError(f"NFL_V2K_DRIVE_START_UNRESOLVED:{game_id}:{drive_id}")
        candidates.sort(key=lambda x: x[0])

        out.append(NormalizedDriveRow(
            game_id=game_id,
            drive_id=drive_id,
            kickoff_utc=kickoff,
            offense=offense,
            defense=defense,
            start_yard=candidates[0][1],
            outcome=outcome,
        ))

    out.sort(key=lambda r: (r.kickoff_utc, r.game_id, int(r.drive_id)))
    return out


def provenance_contract() -> dict:
    return {
        "schema": SCHEMA,
        "drive_identity": ["game_id", "fixed_drive"],
        "provider_drive_fields": ["fixed_drive", "fixed_drive_result"],
        "provider_field_position": "yardline_100",
        "provider_field_position_semantic": "yards_to_opponent_end_zone_for_posteam",
        "normalized_start_yard_formula": "100 - yardline_100",
        "first_usable_play_order": "minimum play_id after non-scrimmage exclusion",
        "unknown_result_behavior": "BLOCK",
        "missing_start_behavior": "BLOCK",
        "fit_stack_imported": False,
        "simulator_stack_imported": False,
        "sportsbook_fields_consumed": [],
        "model_fit_invoked": False,
        "evaluation_invoked": False,
        "readout_consumed": False,
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
