"""Frozen four-attempt CFB candidate bakeoff with deterministic null control.

This is historical engineering selection only, never promotion evidence. Real execution
requires explicit authorization plus green preregistration and acquisition-readiness
reports. The module performs no network calls.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from math import sqrt
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .candidate_model_v2 import fit_cfb_candidate_score_model
from .candidate_registry_v2 import EQUAL, RELIABILITY, BLEND, GAMES
from .fit_policy import DEFAULT_CFB_RIDGE_ALPHA_GRID

CFB_CANDIDATE_BAKEOFF_VERSION = "CFB_CANDIDATE_BAKEOFF_V1"
ATTEMPT_AUTHORIZATION = "CONSUME_FROZEN_ATTEMPTS_1_TO_4"
FAMILIES = (EQUAL, RELIABILITY, BLEND, GAMES)
NULL_SHUFFLE_COUNT = 200


class CFBCandidateBakeoffError(ValueError):
    pass


def _season(row: Mapping[str, Any]) -> int:
    try:
        return int(row["season"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_SEASON_INVALID") from exc


def _joint_rmse(model: Any, rows: Sequence[Mapping[str, Any]]) -> float:
    if not rows:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_VALIDATION_EMPTY")
    squared = 0.0
    for row in rows:
        home_pred, away_pred = model.predict_means(row)
        try:
            home, away = float(row["home_score"]), float(row["away_score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CFBCandidateBakeoffError("CFB_BAKEOFF_SCORE_INVALID") from exc
        squared += (home_pred - home) ** 2 + (away_pred - away) ** 2
    return sqrt(squared / (2.0 * len(rows)))


def _select_alpha(
    rows: Sequence[Mapping[str, Any]],
    *,
    family: str,
    alpha_grid: Sequence[float],
) -> tuple[float, list[dict[str, Any]]]:
    seasons = sorted({_season(row) for row in rows})
    if len(seasons) < 3:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_INNER_SEASONS_INSUFFICIENT")
    scored: list[dict[str, Any]] = []
    for alpha in sorted({float(value) for value in alpha_grid}):
        fold_scores: list[float] = []
        for validation_season in seasons[2:]:
            train = [row for row in rows if _season(row) < validation_season]
            valid = [row for row in rows if _season(row) == validation_season]
            if len(train) < 20 or not valid:
                raise CFBCandidateBakeoffError("CFB_BAKEOFF_INNER_FOLD_INVALID")
            model = fit_cfb_candidate_score_model(train, family=family, ridge_alpha=alpha)
            fold_scores.append(_joint_rmse(model, valid))
        scored.append({"alpha": alpha, "fold_rmse": fold_scores, "mean_rmse": fmean(fold_scores)})
    winner = min(scored, key=lambda item: (item["mean_rmse"], item["alpha"]))
    return float(winner["alpha"]), scored


def evaluate_candidate(
    rows: Iterable[Mapping[str, Any]],
    *,
    family: str,
    alpha_grid: Sequence[float] = DEFAULT_CFB_RIDGE_ALPHA_GRID,
) -> dict[str, Any]:
    data = [dict(row) for row in rows]
    seasons = sorted({_season(row) for row in data})
    if len(seasons) < 4:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_OUTER_SEASONS_INSUFFICIENT")
    folds: list[dict[str, Any]] = []
    scores: list[float] = []
    for validation_season in seasons[3:]:
        train = [row for row in data if _season(row) < validation_season]
        valid = [row for row in data if _season(row) == validation_season]
        alpha, inner = _select_alpha(train, family=family, alpha_grid=alpha_grid)
        model = fit_cfb_candidate_score_model(train, family=family, ridge_alpha=alpha)
        score = _joint_rmse(model, valid)
        scores.append(score)
        folds.append({
            "validation_season": validation_season,
            "train_seasons": sorted({_season(row) for row in train}),
            "selected_alpha": alpha,
            "joint_home_away_score_rmse": score,
            "inner_alpha_selection": inner,
        })
    return {
        "family": family,
        "selection_metric": "MEAN_EXPANDING_SEASON_JOINT_HOME_AWAY_SCORE_RMSE",
        "mean_rmse": fmean(scores),
        "folds": folds,
        "promotion_evidence": False,
        "model_p_created": False,
    }


def _shuffle_labels(rows: Sequence[Mapping[str, Any]], *, rng: np.random.Generator) -> list[dict[str, Any]]:
    """Permute paired realized labels within each season while preserving feature rows."""
    output = [deepcopy(dict(row)) for row in rows]
    by_season: dict[int, list[int]] = {}
    for index, row in enumerate(output):
        by_season.setdefault(_season(row), []).append(index)
    for indices in by_season.values():
        labels = [(output[i]["home_score"], output[i]["away_score"]) for i in indices]
        order = rng.permutation(len(indices)).tolist()
        for target, source_index in zip(indices, order):
            output[target]["home_score"], output[target]["away_score"] = labels[source_index]
    return output


def _seed(seed_material: str, shuffle_index: int) -> int:
    raw = f"{seed_material}|{CFB_CANDIDATE_BAKEOFF_VERSION}|{shuffle_index}".encode("utf-8")
    return int.from_bytes(sha256(raw).digest()[:8], "big", signed=False)


def run_null_control(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed_material: str,
    shuffle_count: int = NULL_SHUFFLE_COUNT,
) -> dict[str, Any]:
    if shuffle_count != NULL_SHUFFLE_COUNT:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_NULL_SHUFFLE_COUNT_MUST_BE_200")
    improvements: dict[str, list[float]] = {family: [] for family in FAMILIES if family != EQUAL}
    for index in range(shuffle_count):
        shuffled = _shuffle_labels(rows, rng=np.random.default_rng(_seed(seed_material, index)))
        scores = {family: evaluate_candidate(shuffled, family=family)["mean_rmse"] for family in FAMILIES}
        baseline = float(scores[EQUAL])
        for family in improvements:
            improvements[family].append(baseline - float(scores[family]))
    thresholds = {
        family: float(np.percentile(values, 95.0, method="linear"))
        for family, values in improvements.items()
    }
    return {
        "shuffle_count": shuffle_count,
        "seed_policy": "SHA256_VERSIONED_PER_SHUFFLE_TO_NUMPY_PCG64",
        "threshold": "95TH_PERCENTILE_OF_NULL_CANDIDATE_IMPROVEMENT_DISTRIBUTION",
        "candidate_improvement_statistic": "BASELINE_EQUAL_WEIGHT_RMSE_MINUS_CANDIDATE_RMSE",
        "improvements": improvements,
        "thresholds": thresholds,
    }


def run_frozen_four_candidate_bakeoff(
    rows: Iterable[Mapping[str, Any]],
    *,
    authorization: str,
    prereg_binding: Mapping[str, Any],
    acquisition_readiness: Mapping[str, Any],
    seed_material: str,
) -> dict[str, Any]:
    if authorization != ATTEMPT_AUTHORIZATION:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_EXPLICIT_FOUR_ATTEMPT_AUTHORIZATION_REQUIRED")
    if prereg_binding.get("status") != "READY_FOR_FIRST_EVALUATION":
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_PREREG_BINDING_NOT_READY")
    if acquisition_readiness.get("status") != "READY_FOR_HISTORICAL_REPLAY":
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_ACQUISITION_NOT_READY")
    if prereg_binding.get("attempts_consumed") != 0:
        raise CFBCandidateBakeoffError("CFB_BAKEOFF_REQUIRES_ZERO_PRIOR_ATTEMPTS")
    data = [dict(row) for row in rows]
    observed = {family: evaluate_candidate(data, family=family) for family in FAMILIES}
    null = run_null_control(data, seed_material=seed_material)
    baseline = float(observed[EQUAL]["mean_rmse"])
    qualified: list[str] = []
    comparisons: dict[str, Any] = {}
    for family in FAMILIES[1:]:
        improvement = baseline - float(observed[family]["mean_rmse"])
        threshold = float(null["thresholds"][family])
        clears = improvement > threshold
        comparisons[family] = {
            "observed_improvement": improvement,
            "null_95_threshold": threshold,
            "clears_null_threshold": clears,
        }
        if clears:
            qualified.append(family)
    if qualified:
        order = {family: index for index, family in enumerate(FAMILIES)}
        winner = min(qualified, key=lambda family: (observed[family]["mean_rmse"], order[family]))
        outcome = "CANDIDATE_SELECTED_FOR_FREEZE"
    else:
        winner = None
        outcome = "NO_CANDIDATE_DEMONSTRATED_SIGNAL_AT_THIS_SAMPLE"
    return {
        "schema": CFB_CANDIDATE_BAKEOFF_VERSION,
        "outcome": outcome,
        "winner": winner,
        "results": observed,
        "null_control": null,
        "comparisons": comparisons,
        "attempts_consumed_by_run": 4,
        "attempts_remaining_after_run": 0,
        "promotion_evidence": False,
        "historical_pit_created": False,
        "model_p_created": False,
        "truth_gate_pass_granted": False,
        "official_status_granted": False,
    }


__all__ = [
    "ATTEMPT_AUTHORIZATION",
    "CFBCandidateBakeoffError",
    "FAMILIES",
    "NULL_SHUFFLE_COUNT",
    "evaluate_candidate",
    "run_frozen_four_candidate_bakeoff",
    "run_null_control",
]
