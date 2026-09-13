"""Unactivated exact-math runtime cache for the preregistered NFL V2J readout.

This module exists only as a contingency if the frozen first-readout workflow hits
its hosted-runner timeout.  It deliberately keeps the same conditional drive
probabilities, ``np.outer`` construction, masked ``sum`` operations, and
accumulation order as ``m2_v2j_validation._market_readout``.  The only reused
objects are deterministic repeated convolutions, safety PMFs, and integer support
masks whose values do not depend on the shared-environment probability weights.

Nothing imports this module from the active V2J workflow.  It grants no Model_P,
promotion, staking, OFFICIAL, or rerun authority.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .m2_v2i_candidate import _combine_pmfs, _repeat_convolution, _safety_pmf, _safety_probability
from .m2_v2j_candidate import conditioned_drive_probabilities
from .m2_v2j_validation import _KEYS, _clip, _float


class NFLV2JRuntimeCacheError(ValueError):
    pass


def market_readout_exact_cached(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Return the V2J market readout while reusing exact deterministic work.

    Floating-point probability operations intentionally remain in the same order
    as the frozen reference implementation.  If score support ever changes across
    shared-environment rows, this contingency fails closed rather than applying a
    stale mask.
    """
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    hf = row.get("home_features")
    af = row.get("away_features")
    if not home or not away or home == away or not isinstance(hf, dict) or not isinstance(af, dict):
        raise ValueError("NFL_M2_V2J_PREDICTION_IDENTITY_INVALID")

    spread_line = _float(row.get("spread_line"))
    total_line = _float(row.get("total_line"))
    base = model.base_drive_model
    home_safety_p = _safety_probability(base, home, away)
    away_safety_p = _safety_probability(base, away, home)
    regimes = tuple(base.possession_regime)

    home_safety = {
        int(away_drives): _safety_pmf(int(away_drives), home_safety_p)
        for _, away_drives, _ in regimes
    }
    away_safety = {
        int(home_drives): _safety_pmf(int(home_drives), away_safety_p)
        for home_drives, _, _ in regimes
    }

    spread_win = spread_push = total_win = total_push = total_weight = 0.0
    key_profile = {str(key): 0.0 for key in _KEYS}
    masks: dict[tuple[int, int], dict[str, Any]] = {}

    for env, env_weight in model.shared_environment:
        home_drive = conditioned_drive_probabilities(
            model,
            offense=home,
            defense=away,
            offense_features=hf,
            defense_features=af,
            shared_environment=env,
        )
        away_drive = conditioned_drive_probabilities(
            model,
            offense=away,
            defense=home,
            offense_features=af,
            defense_features=hf,
            shared_environment=env,
        )

        home_offense: dict[int, dict[int, float]] = {}
        away_offense: dict[int, dict[int, float]] = {}

        for home_drives, away_drives, regime_weight in regimes:
            hd = int(home_drives)
            ad = int(away_drives)
            if hd not in home_offense:
                home_offense[hd] = _repeat_convolution(home_drive, hd)
            if ad not in away_offense:
                away_offense[ad] = _repeat_convolution(away_drive, ad)

            home_scores = _combine_pmfs(home_offense[hd], home_safety[ad])
            away_scores = _combine_pmfs(away_offense[ad], away_safety[hd])
            home_values = np.fromiter(home_scores.keys(), dtype=np.int64)
            home_probs = np.fromiter(home_scores.values(), dtype=np.float64)
            away_values = np.fromiter(away_scores.keys(), dtype=np.int64)
            away_probs = np.fromiter(away_scores.values(), dtype=np.float64)

            regime_key = (hd, ad)
            bundle = masks.get(regime_key)
            if bundle is None:
                margins = home_values[:, None] - away_values[None, :]
                totals = home_values[:, None] + away_values[None, :]
                bundle = {
                    "home_values": tuple(int(x) for x in home_values),
                    "away_values": tuple(int(x) for x in away_values),
                    "key_masks": {key: (margins == key) for key in _KEYS},
                    "spread_win": None if spread_line is None else (margins > spread_line),
                    "spread_push": None if spread_line is None else (margins == spread_line),
                    "total_win": None if total_line is None else (totals > total_line),
                    "total_push": None if total_line is None else (totals == total_line),
                }
                masks[regime_key] = bundle
            else:
                if bundle["home_values"] != tuple(int(x) for x in home_values) or bundle["away_values"] != tuple(int(x) for x in away_values):
                    raise NFLV2JRuntimeCacheError("NFL_M2_V2J_SCORE_SUPPORT_CHANGED_ACROSS_ENVIRONMENT")

            weights = float(env_weight) * float(regime_weight) * np.outer(home_probs, away_probs)
            total_weight += float(weights.sum())
            for key in _KEYS:
                key_profile[str(key)] += float(weights[bundle["key_masks"][key]].sum())
            if spread_line is not None:
                spread_win += float(weights[bundle["spread_win"]].sum())
                spread_push += float(weights[bundle["spread_push"]].sum())
            if total_line is not None:
                total_win += float(weights[bundle["total_win"]].sum())
                total_push += float(weights[bundle["total_push"]].sum())

    if abs(total_weight - 1.0) > 1e-8:
        raise ValueError("NFL_M2_V2J_WEIGHT_CONSERVATION_FAILED")
    home_cover = None if spread_line is None or total_weight <= spread_push else _clip(spread_win / (total_weight - spread_push))
    over = None if total_line is None or total_weight <= total_push else _clip(total_win / (total_weight - total_push))
    return {
        "spread_line": spread_line,
        "total_line": total_line,
        "m2_home_cover_prob": home_cover,
        "m2_over_prob": over,
        "candidate_signed_key_probability": key_profile,
    }
