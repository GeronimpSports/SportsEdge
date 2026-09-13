"""Executable preregistered CFB candidate-family primitives.

This module contains no evaluation results and consumes no model-selection attempt.
All four frozen families are specified prospectively. Candidate constants are frozen
in code and must match preregistration before evaluation.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, Mapping

FAMILY_EQUAL_WEIGHT_HARD_SWITCH = "EQUAL_WEIGHT_HARD_SWITCH"
FAMILY_RELIABILITY_WEIGHTED_HARD_SWITCH = "RELIABILITY_WEIGHTED_HARD_SWITCH"
FAMILY_PRIOR_CURRENT_BLEND = "PRIOR_CURRENT_BLEND"
FAMILY_GAMES_IN_SAMPLE_FEATURE = "GAMES_IN_SAMPLE_FEATURE"

RELIABILITY_SWITCH_MIN_GAMES = 3
PRIOR_BLEND_FULL_CURRENT_GAMES = 4

IMPLEMENTED_FAMILIES = frozenset({
    FAMILY_EQUAL_WEIGHT_HARD_SWITCH,
    FAMILY_RELIABILITY_WEIGHTED_HARD_SWITCH,
    FAMILY_PRIOR_CURRENT_BLEND,
    FAMILY_GAMES_IN_SAMPLE_FEATURE,
})

TEAM_METRIC_KEYS = (
    "off_ppa_rush", "off_ppa_dropback", "def_ppa_rush_allowed", "def_ppa_dropback_allowed",
    "off_success_rate", "def_success_rate_allowed", "standard_down_ppa",
    "passing_down_success_rate", "eckel_rate", "points_per_eckel", "points_per_drive",
    "net_field_position", "explosive_rate",
)

BANNED_MARKET_KEYS = frozenset({
    "spread", "spread_line", "total", "total_line", "line", "price",
    "american_odds", "decimal_odds", "implied_probability", "implied_prob",
    "market_probability", "novig_prob", "no_vig_prob", "book", "sportsbook",
    "closing_line", "closing_price", "home_moneyline", "away_moneyline", "odds",
})

class CFBCandidateFamilyError(ValueError):
    pass


def _assert_market_blind(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).strip().lower()
            if name in BANNED_MARKET_KEYS or "implied_prob" in name or "novig" in name or "no_vig" in name:
                raise CFBCandidateFamilyError(f"CFB_CANDIDATE_MARKET_DATA_PROHIBITED:{path}.{key}")
            _assert_market_blind(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            _assert_market_blind(child, f"{path}[{idx}]")


def _finite(value: Any, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_NUMERIC_REQUIRED:{name}") from exc
    if not isfinite(out):
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_NONFINITE:{name}")
    return out


def _metrics(row: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    metrics = row.get(field)
    if not isinstance(metrics, Mapping):
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_{field.upper()}_REQUIRED")
    missing = [key for key in TEAM_METRIC_KEYS if key not in metrics]
    if missing:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_METRIC_FIELDS_MISSING:{field}:{','.join(missing)}")
    return metrics


def _season_week(row: Mapping[str, Any]) -> tuple[int, int]:
    try:
        season, week = int(row["season"]), int(row["week"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBCandidateFamilyError("CFB_CANDIDATE_SEASON_WEEK_INVALID") from exc
    if week < 1:
        raise CFBCandidateFamilyError("CFB_CANDIDATE_WEEK_INVALID")
    return season, week


def _validate_prior(metrics: Mapping[str, Any], *, season: int, side: str) -> None:
    try:
        metric_season = int(metrics["season"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_{side.upper()}_PRIOR_IDENTITY_INVALID") from exc
    if str(metrics.get("sample_source") or "").upper() != "PRIOR_SEASON_FALLBACK" or metric_season != season - 1:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_PRIOR_SEASON_INVALID:{side}")


def _validate_current(metrics: Mapping[str, Any], *, season: int, week: int, side: str) -> None:
    try:
        metric_season, through_week = int(metrics["season"]), int(metrics["through_week"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_{side.upper()}_CURRENT_IDENTITY_INVALID") from exc
    if (str(metrics.get("sample_source") or "").upper() != "CURRENT_SEASON_PRIOR_WEEKS"
            or metric_season != season or through_week != week - 1):
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_CURRENT_SEASON_INVALID:{side}")


def _games(row: Mapping[str, Any], side: str) -> int:
    raw = row.get(f"{side}_games_in_sample")
    if isinstance(raw, bool):
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_GAMES_IN_SAMPLE_INVALID:{side}")
    try:
        out = int(raw)
    except (TypeError, ValueError) as exc:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_GAMES_IN_SAMPLE_INVALID:{side}") from exc
    if out < 0:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_GAMES_IN_SAMPLE_NEGATIVE:{side}")
    return out


def _clean(row: Mapping[str, Any]) -> None:
    _assert_market_blind({k: v for k, v in row.items() if k not in {
        "home_score", "away_score", "regulation_home_score", "regulation_away_score"
    }})


def materialize_equal_weight_hard_switch(row: Mapping[str, Any]) -> dict[str, Any]:
    _clean(row)
    season, week = _season_week(row)
    for side in ("home", "away"):
        metrics = _metrics(row, f"{side}_metrics")
        if week == 1:
            _validate_prior(metrics, season=season, side=side)
        else:
            _validate_current(metrics, season=season, week=week, side=side)
    return deepcopy(dict(row))


def _sources(row: Mapping[str, Any], side: str, season: int, week: int):
    prior = _metrics(row, f"{side}_prior_metrics")
    _validate_prior(prior, season=season, side=side)
    if week == 1:
        return prior, None
    current = _metrics(row, f"{side}_current_metrics")
    _validate_current(current, season=season, week=week, side=side)
    return prior, current


def materialize_reliability_weighted_hard_switch(row: Mapping[str, Any]) -> dict[str, Any]:
    """Prior metrics until >=3 current-season games; then hard switch to current."""
    _clean(row)
    season, week = _season_week(row)
    out = deepcopy(dict(row))
    for side in ("home", "away"):
        prior, current = _sources(out, side, season, week)
        selected = prior if week == 1 or _games(out, side) < RELIABILITY_SWITCH_MIN_GAMES else current
        out[f"{side}_metrics"] = deepcopy(dict(selected))
    return out


def materialize_prior_current_blend(row: Mapping[str, Any]) -> dict[str, Any]:
    """Linear prior/current blend; current weight reaches 1.0 after four games."""
    _clean(row)
    season, week = _season_week(row)
    out = deepcopy(dict(row))
    for side in ("home", "away"):
        prior, current = _sources(out, side, season, week)
        weight = 0.0 if current is None else min(_games(out, side) / float(PRIOR_BLEND_FULL_CURRENT_GAMES), 1.0)
        blended = deepcopy(dict(prior if current is None else current))
        for key in TEAM_METRIC_KEYS:
            pv = _finite(prior[key], f"{side}.prior.{key}")
            cv = pv if current is None else _finite(current[key], f"{side}.current.{key}")
            blended[key] = (1.0 - weight) * pv + weight * cv
        blended["sample_source"] = "PRIOR_CURRENT_BLEND"
        blended["season"] = season
        blended["through_week"] = max(0, week - 1)
        blended["blend_current_weight"] = weight
        out[f"{side}_metrics"] = blended
    return out


def materialize_games_in_sample_feature(row: Mapping[str, Any]) -> dict[str, Any]:
    out = materialize_equal_weight_hard_switch(row)
    out["candidate_extra_features"] = {
        "home_games_in_sample": float(_games(out, "home")),
        "away_games_in_sample": float(_games(out, "away")),
    }
    return out


def candidate_extra_feature_names(family: str) -> tuple[str, ...]:
    if family == FAMILY_GAMES_IN_SAMPLE_FEATURE:
        return ("home_games_in_sample", "away_games_in_sample")
    if family in IMPLEMENTED_FAMILIES:
        return ()
    raise CFBCandidateFamilyError(f"CFB_CANDIDATE_FAMILY_UNIMPLEMENTED:{family}")


def materialize_candidate_row(family: str, row: Mapping[str, Any], *, constants: Mapping[str, Any] | None = None) -> dict[str, Any]:
    supplied = dict(constants or {})
    if family == FAMILY_EQUAL_WEIGHT_HARD_SWITCH:
        if supplied:
            raise CFBCandidateFamilyError("CFB_EQUAL_WEIGHT_BASELINE_CONSTANTS_PROHIBITED")
        return materialize_equal_weight_hard_switch(row)
    if family == FAMILY_RELIABILITY_WEIGHTED_HARD_SWITCH:
        if supplied != {"min_current_games": RELIABILITY_SWITCH_MIN_GAMES}:
            raise CFBCandidateFamilyError("CFB_RELIABILITY_SWITCH_CONSTANTS_MISMATCH")
        return materialize_reliability_weighted_hard_switch(row)
    if family == FAMILY_PRIOR_CURRENT_BLEND:
        if supplied != {"full_current_games": PRIOR_BLEND_FULL_CURRENT_GAMES}:
            raise CFBCandidateFamilyError("CFB_PRIOR_CURRENT_BLEND_CONSTANTS_MISMATCH")
        return materialize_prior_current_blend(row)
    if family == FAMILY_GAMES_IN_SAMPLE_FEATURE:
        if supplied:
            raise CFBCandidateFamilyError("CFB_GAMES_IN_SAMPLE_CONSTANTS_PROHIBITED")
        return materialize_games_in_sample_feature(row)
    raise CFBCandidateFamilyError(f"CFB_CANDIDATE_FAMILY_UNIMPLEMENTED:{family}")


__all__ = [
    "CFBCandidateFamilyError", "FAMILY_EQUAL_WEIGHT_HARD_SWITCH",
    "FAMILY_RELIABILITY_WEIGHTED_HARD_SWITCH", "FAMILY_PRIOR_CURRENT_BLEND",
    "FAMILY_GAMES_IN_SAMPLE_FEATURE", "IMPLEMENTED_FAMILIES", "TEAM_METRIC_KEYS",
    "RELIABILITY_SWITCH_MIN_GAMES", "PRIOR_BLEND_FULL_CURRENT_GAMES",
    "candidate_extra_feature_names", "materialize_candidate_row",
]
