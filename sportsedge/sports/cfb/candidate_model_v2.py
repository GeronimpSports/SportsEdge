"""Executable four-family CFB candidate model surface.

This module converts each preregistered candidate transform into the exact numeric
feature vector consumed by fitting. It performs no candidate evaluation and creates
no Model_P/promotion authority. The games-in-sample family appends its two frozen
sample-size features so they cannot be silently ignored by the baseline vector.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

import numpy as np

from .candidate_registry_v2 import EQUAL, RELIABILITY, BLEND, GAMES, materialize_candidate_row
from .joint_model import _feature_names, _feature_vector, _ridge

CFB_CANDIDATE_MODEL_SURFACE_VERSION = "CFB_CANDIDATE_MODEL_SURFACE_V2"
GAMES_EXTRA_FEATURE_NAMES = ("home_games_in_sample_feature", "away_games_in_sample_feature")


class CFBCandidateModelError(ValueError):
    pass


def candidate_feature_names(family: str) -> tuple[str, ...]:
    base = _feature_names()
    if family == GAMES:
        return base + GAMES_EXTRA_FEATURE_NAMES
    if family in {EQUAL, RELIABILITY, BLEND}:
        return base
    raise CFBCandidateModelError(f"CFB_CANDIDATE_FAMILY_UNKNOWN:{family}")


def candidate_feature_vector(family: str, row: Mapping[str, Any]) -> np.ndarray:
    """Return the exact numeric vector for a frozen candidate family."""
    transformed = materialize_candidate_row(family, row)
    base = _feature_vector(transformed)
    if family != GAMES:
        return base
    extras = []
    for key in GAMES_EXTRA_FEATURE_NAMES:
        try:
            value = float(transformed[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise CFBCandidateModelError(f"CFB_CANDIDATE_EXTRA_FEATURE_MISSING:{key}") from exc
        if not isfinite(value):
            raise CFBCandidateModelError(f"CFB_CANDIDATE_EXTRA_FEATURE_NONFINITE:{key}")
        extras.append(value)
    return np.concatenate((base, np.asarray(extras, dtype=float)))


@dataclass(frozen=True)
class CFBCandidateScoreModel:
    family: str
    feature_names: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    home_coefficients: tuple[float, ...]
    away_coefficients: tuple[float, ...]
    ridge_alpha: float

    def predict_means(self, row: Mapping[str, Any]) -> tuple[float, float]:
        raw = candidate_feature_vector(self.family, row)
        means = np.asarray(self.feature_means, dtype=float)
        scales = np.asarray(self.feature_scales, dtype=float)
        if raw.shape != means.shape:
            raise CFBCandidateModelError("CFB_CANDIDATE_FEATURE_DIMENSION_MISMATCH")
        design = np.concatenate(([1.0], (raw - means) / scales))
        home = float(design @ np.asarray(self.home_coefficients, dtype=float))
        away = float(design @ np.asarray(self.away_coefficients, dtype=float))
        if not isfinite(home) or not isfinite(away):
            raise CFBCandidateModelError("CFB_CANDIDATE_PREDICTION_NONFINITE")
        return home, away


def fit_cfb_candidate_score_model(
    rows: Iterable[Mapping[str, Any]],
    *,
    family: str,
    ridge_alpha: float,
) -> CFBCandidateScoreModel:
    """Fit one frozen family on caller-supplied training rows only."""
    data = [dict(row) for row in rows]
    if len(data) < 20:
        raise CFBCandidateModelError("CFB_CANDIDATE_TRAINING_ROWS_INSUFFICIENT")
    try:
        alpha = float(ridge_alpha)
    except (TypeError, ValueError) as exc:
        raise CFBCandidateModelError("CFB_CANDIDATE_RIDGE_ALPHA_INVALID") from exc
    if not isfinite(alpha) or alpha < 0:
        raise CFBCandidateModelError("CFB_CANDIDATE_RIDGE_ALPHA_INVALID")

    raw = np.asarray([candidate_feature_vector(family, row) for row in data], dtype=float)
    means, scales = raw.mean(axis=0), raw.std(axis=0)
    scales = np.where(scales > 1e-12, scales, 1.0)
    design = np.column_stack((np.ones(len(data)), (raw - means) / scales))
    try:
        home_y = np.asarray([float(row["home_score"]) for row in data], dtype=float)
        away_y = np.asarray([float(row["away_score"]) for row in data], dtype=float)
    except (KeyError, TypeError, ValueError) as exc:
        raise CFBCandidateModelError("CFB_CANDIDATE_SCORE_INVALID") from exc
    if not np.all(np.isfinite(home_y)) or not np.all(np.isfinite(away_y)):
        raise CFBCandidateModelError("CFB_CANDIDATE_SCORE_NONFINITE")

    home_coef = _ridge(design, home_y, alpha)
    away_coef = _ridge(design, away_y, alpha)
    return CFBCandidateScoreModel(
        family=family,
        feature_names=candidate_feature_names(family),
        feature_means=tuple(map(float, means)),
        feature_scales=tuple(map(float, scales)),
        home_coefficients=tuple(map(float, home_coef)),
        away_coefficients=tuple(map(float, away_coef)),
        ridge_alpha=alpha,
    )


__all__ = [
    "CFB_CANDIDATE_MODEL_SURFACE_VERSION",
    "CFBCandidateModelError",
    "CFBCandidateScoreModel",
    "GAMES_EXTRA_FEATURE_NAMES",
    "candidate_feature_names",
    "candidate_feature_vector",
    "fit_cfb_candidate_score_model",
]
