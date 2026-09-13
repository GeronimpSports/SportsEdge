"""Research-only NFL V2J conditioned-drive shared-regime candidate.

Preregistered by config/research/nfl_v2j_conditioned_drive_regime_prereg_2026-09-12.json.
This module has no production Model_P, promotion, staking, OFFICIAL, market-eligibility,
or registry authority. Sportsbook prices are rejected as model inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Any, Iterable, Mapping

from sportsedge.sports.nfl.m2 import NFL_M2_FEATURE_CONTRACT, BANNED_MARKET_ALIASES, BANNED_MARKET_KEYS
from sportsedge.sports.nfl.m2_v2i_candidate import (
    NFLM2V2ICandidateModel,
    fit_nfl_m2_v2i_candidate,
    _offense_drive_probabilities,
)

NFL_M2_V2J_CANDIDATE_MODEL_ID = "nfl_v2j_conditioned_drive_regime_candidate"
NFL_M2_V2J_DISTRIBUTION_CONTRACT = "NFL_M2_V2J_CONDITIONED_DRIVE_SHARED_ENV_V1"

_CONDITIONING_FEATURES = (
    "adj_off_epa", "adj_def_epa", "pass_epa", "rush_epa", "pressure_for",
    "pressure_allowed", "success_rate", "explosive_rate", "rest_diff_days",
    "travel_miles", "timezone_crossings", "short_week", "bye_week", "wind_mph",
    "roof_closed", "qb_adjustment", "prior_efficiency", "prior_weight",
)


def _assert_market_blind(value: Any, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).strip().lower()
            if name in BANNED_MARKET_KEYS or name in BANNED_MARKET_ALIASES or "implied_prob" in name or "novig_prob" in name or "no_vig_prob" in name:
                raise ValueError(f"NFL_M2_V2J_MARKET_DATA_PROHIBITED:{path}.{key}")
            _assert_market_blind(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_market_blind(child, f"{path}[{index}]")


def _feature_vector(features: Mapping[str, Any]) -> tuple[float, ...]:
    _assert_market_blind(features)
    if features.get("feature_contract") != NFL_M2_FEATURE_CONTRACT:
        raise ValueError("NFL_M2_V2J_FEATURE_CONTRACT_REQUIRED")
    if not str(features.get("qb_id") or "").strip() or not str(features.get("feature_asof_ts") or "").strip():
        raise ValueError("NFL_M2_V2J_FEATURE_IDENTITY_REQUIRED")
    out = []
    for key in _CONDITIONING_FEATURES:
        if key not in features:
            raise ValueError(f"NFL_M2_V2J_FEATURE_MISSING:{key}")
        value = float(features[key])
        if not isfinite(value):
            raise ValueError(f"NFL_M2_V2J_FEATURE_NONFINITE:{key}")
        out.append(value)
    return tuple(out)


def _logit(p: float) -> float:
    q = min(1.0 - 1e-9, max(1e-9, float(p)))
    return log(q / (1.0 - q))


def _logistic(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


@dataclass(frozen=True)
class NFLM2V2JCandidateModel:
    model_id: str
    distribution_contract: str
    base_drive_model: NFLM2V2ICandidateModel
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    conditioning_weights: tuple[float, ...]
    shared_environment: tuple[tuple[float, float], ...]


def fit_nfl_m2_v2j_candidate(
    event_rows: Iterable[Mapping[str, Any]],
    feature_rows: Iterable[Mapping[str, Any]],
) -> NFLM2V2JCandidateModel:
    events = [dict(row) for row in event_rows]
    rows = [dict(row) for row in feature_rows]
    if len(events) < 2 or len(rows) < 2:
        raise ValueError("NFL_M2_V2J_TRAINING_ROWS_INSUFFICIENT")
    base = fit_nfl_m2_v2i_candidate(events)

    vectors: list[tuple[float, ...]] = []
    residuals: list[float] = []
    for row in rows:
        home = row.get("home_features")
        away = row.get("away_features")
        if not isinstance(home, Mapping) or not isinstance(away, Mapping):
            raise ValueError("NFL_M2_V2J_GAME_FEATURES_REQUIRED")
        hv, av = _feature_vector(home), _feature_vector(away)
        vector = tuple(h - a for h, a in zip(hv, av))
        vectors.append(vector)
        home_score = float(row["home_score"])
        away_score = float(row["away_score"])
        if not isfinite(home_score) or not isfinite(away_score):
            raise ValueError("NFL_M2_V2J_SCORE_NONFINITE")
        residuals.append(home_score - away_score)

    dim = len(vectors[0])
    means = tuple(sum(v[i] for v in vectors) / len(vectors) for i in range(dim))
    scales = []
    for i in range(dim):
        var = sum((v[i] - means[i]) ** 2 for v in vectors) / len(vectors)
        scales.append(var ** 0.5 if var > 1e-12 else 1.0)

    # Fixed preregistered-strength direction: no post-readout tuning. Coefficients are
    # estimated only from training-row covariance with realized margin, ridge-stabilized.
    centered_y = [y - (sum(residuals) / len(residuals)) for y in residuals]
    weights = []
    ridge = float(len(vectors))
    for i in range(dim):
        xs = [(v[i] - means[i]) / scales[i] for v in vectors]
        numerator = sum(x * y for x, y in zip(xs, centered_y))
        denominator = sum(x * x for x in xs) + ridge
        weights.append(numerator / denominator)

    strength = [sum(((v[i] - means[i]) / scales[i]) * weights[i] for i in range(dim)) for v in vectors]
    margin_mean = sum(residuals) / len(residuals)
    env_raw = [y - margin_mean - s for y, s in zip(residuals, strength)]
    env_scale = max(1.0, (sum(e * e for e in env_raw) / len(env_raw)) ** 0.5)
    # Shared environment support is learned from training residuals only and centered.
    shared_environment = tuple((e / env_scale, 1.0 / len(env_raw)) for e in sorted(env_raw))

    return NFLM2V2JCandidateModel(
        model_id=NFL_M2_V2J_CANDIDATE_MODEL_ID,
        distribution_contract=NFL_M2_V2J_DISTRIBUTION_CONTRACT,
        base_drive_model=base,
        feature_means=means,
        feature_scales=tuple(scales),
        conditioning_weights=tuple(weights),
        shared_environment=shared_environment,
    )


def conditioned_drive_probabilities(
    model: NFLM2V2JCandidateModel,
    *,
    offense: str,
    defense: str,
    offense_features: Mapping[str, Any],
    defense_features: Mapping[str, Any],
    shared_environment: float = 0.0,
) -> dict[int, float]:
    ov = _feature_vector(offense_features)
    dv = _feature_vector(defense_features)
    if len(ov) != len(model.feature_means) or len(dv) != len(model.feature_means):
        raise ValueError("NFL_M2_V2J_FEATURE_DIMENSION_MISMATCH")
    diff = [(o - d - model.feature_means[i]) / model.feature_scales[i] for i, (o, d) in enumerate(zip(ov, dv))]
    strength = sum(x * w for x, w in zip(diff, model.conditioning_weights))
    strength = max(-2.5, min(2.5, strength / 14.0 + float(shared_environment) * 0.12))

    base = _offense_drive_probabilities(model.base_drive_model, offense, defense)
    scoring_base = 1.0 - base.get(0, 0.0)
    scoring_new = _logistic(_logit(scoring_base) + strength)
    if scoring_base <= 0.0:
        return dict(base)
    scale = scoring_new / scoring_base
    out = {points: (prob * scale if points != 0 else 1.0 - scoring_new) for points, prob in base.items()}
    total = sum(out.values())
    return {points: prob / total for points, prob in sorted(out.items())}
