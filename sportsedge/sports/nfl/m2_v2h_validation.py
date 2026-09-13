"""First frozen historical readout for preregistered research-only NFL V2H.

No V2H parameter may be changed based on this readout without a new
preregistration. Market prices are evaluation-only and never model features.
"""
from __future__ import annotations

from math import isfinite, log
from typing import Any, Iterable

from sportsedge.core.walkforward.season import season_walk_forward
from .historical_validation import build_calibration_evidence, calibrate_nfl_evaluations, no_vig_two_way
from .m2_v2h_candidate import (
    NFL_M2_V2H_CANDIDATE_MODEL_ID,
    NFL_M2_V2H_DISTRIBUTION_CONTRACT,
    NFL_M2_V2H_EVENT_CONTRACT,
    derive_nfl_m2_v2h_score_distribution,
    fit_nfl_m2_v2h_candidate,
)

_EPS = 1e-9
_KEYS = (-7, -3, 3, 7)


def _float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _clip(value: float) -> float:
    return min(1.0 - _EPS, max(_EPS, float(value)))


def _novig(a: Any, b: Any) -> tuple[float | None, float | None]:
    if a in (None, "") or b in (None, ""):
        return None, None
    try:
        return no_vig_two_way(a, b)
    except ValueError:
        return None, None


def _conditional(distribution, win_predicate, push_predicate) -> float | None:
    win = loss = 0.0
    for item in distribution:
        weight = float(item["weight"])
        if not isfinite(weight) or weight < 0:
            raise ValueError("NFL_M2_V2H_WEIGHT_INVALID")
        if push_predicate(item):
            continue
        if win_predicate(item):
            win += weight
        else:
            loss += weight
    denominator = win + loss
    return None if denominator <= 0 else _clip(win / denominator)


def build_nfl_m2_v2h_raw_evaluations(
    rows: Iterable[dict[str, Any]],
    *,
    min_train_seasons: int = 2,
    prior_drives: float = 48.0,
    max_events_per_type: int = 9,
) -> list[dict[str, Any]]:
    data = [dict(row) for row in rows]
    if not data:
        return []
    folds = season_walk_forward(data, season_key="season", min_train_seasons=min_train_seasons)
    output: list[dict[str, Any]] = []
    for fold in folds:
        model = fit_nfl_m2_v2h_candidate(
            fold.train_rows,
            prior_drives=prior_drives,
            max_events_per_type=max_events_per_type,
        )
        if int(fold.test_season) in model.train_seasons:
            raise ValueError("NFL_M2_V2H_TEST_SEASON_IN_TRAINING")
        for raw in fold.test_rows:
            row = dict(raw)
            distribution = derive_nfl_m2_v2h_score_distribution(model, row)
            if not distribution:
                raise ValueError("NFL_M2_V2H_DISTRIBUTION_EMPTY")
            total_weight = sum(float(item["weight"]) for item in distribution)
            if abs(total_weight - 1.0) > 1e-10:
                raise ValueError("NFL_M2_V2H_WEIGHT_CONSERVATION_FAILED")

            spread_line = _float(row.get("spread_line"))
            total_line = _float(row.get("total_line"))
            candidate_home = None
            candidate_over = None
            if spread_line is not None:
                candidate_home = _conditional(
                    distribution,
                    lambda item: float(item["margin"]) > spread_line,
                    lambda item: float(item["margin"]) == spread_line,
                )
            if total_line is not None:
                candidate_over = _conditional(
                    distribution,
                    lambda item: float(item["total"]) > total_line,
                    lambda item: float(item["total"]) == total_line,
                )

            home_score = _float(row.get("home_score"))
            away_score = _float(row.get("away_score"))
            if home_score is None or away_score is None:
                raise ValueError("NFL_M2_V2H_REALIZED_SCORE_MISSING")
            actual_margin = home_score - away_score
            actual_total = home_score + away_score
            spread_push = spread_line is not None and actual_margin == spread_line
            total_push = total_line is not None and actual_total == total_line
            home_cover = None if spread_line is None or spread_push else int(actual_margin > spread_line)
            over = None if total_line is None or total_push else int(actual_total > total_line)
            m1_home, _ = _novig(row.get("home_spread_odds"), row.get("away_spread_odds"))
            m1_over, _ = _novig(row.get("over_odds"), row.get("under_odds"))
            key_profile = {
                str(key): sum(float(item["weight"]) for item in distribution if int(item["margin"]) == key)
                for key in _KEYS
            }

            output.append({
                "game_id": str(row.get("game_id") or ""),
                "season": int(row["season"]),
                "week": row.get("week"),
                "model_id": model.model_id,
                "distribution_contract": model.distribution_contract,
                "event_contract": model.event_contract,
                "train_seasons": model.train_seasons,
                "spread_line": spread_line,
                "total_line": total_line,
                "spread_push": bool(spread_push),
                "total_push": bool(total_push),
                "home_cover_outcome": home_cover,
                "over_outcome": over,
                "m1_home_cover_prob": m1_home,
                "m1_over_prob": m1_over,
                "m2_home_cover_prob": candidate_home,
                "m2_over_prob": candidate_over,
                "candidate_signed_key_probability": key_profile,
            })
    return output


def _loss(pairs: list[tuple[int, float]]) -> tuple[float, float]:
    if not pairs:
        raise ValueError("NFL_M2_V2H_EMPTY_EVALUATION")
    ll = brier = 0.0
    for outcome, probability in pairs:
        p = _clip(probability)
        ll += -(outcome * log(p) + (1 - outcome) * log(1.0 - p))
        brier += (p - outcome) ** 2
    n = float(len(pairs))
    return ll / n, brier / n


def _fold_rows(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = {
        "spread": ("home_cover_outcome", "m1_home_cover_prob", "m2_home_cover_calibrated_prob"),
        "total": ("over_outcome", "m1_over_prob", "m2_over_calibrated_prob"),
    }
    output = []
    for season in sorted({int(row["season"]) for row in evaluations}):
        season_rows = [row for row in evaluations if int(row["season"]) == season]
        for market, (outcome_key, baseline_key, candidate_key) in specs.items():
            eligible = [row for row in season_rows if row.get(outcome_key) in (0, 1) and row.get(candidate_key) is not None]
            comparable = [row for row in eligible if row.get(baseline_key) is not None]
            if not comparable:
                continue
            baseline_pairs = [(int(row[outcome_key]), float(row[baseline_key])) for row in comparable]
            candidate_pairs = [(int(row[outcome_key]), float(row[candidate_key])) for row in comparable]
            baseline_ll, baseline_brier = _loss(baseline_pairs)
            candidate_ll, candidate_brier = _loss(candidate_pairs)
            output.append({
                "season": season,
                "market": market,
                "n": len(comparable),
                "eligible_n": len(eligible),
                "m1_coverage": len(comparable) / len(eligible),
                "m1_log_loss": baseline_ll,
                "candidate_log_loss": candidate_ll,
                "m1_brier": baseline_brier,
                "candidate_brier": candidate_brier,
                "candidate_beats_m1": candidate_ll < baseline_ll,
                "candidate_probability_source": "V2H_MARKET_BLIND_SCORING_SEQUENCE_DISTRIBUTION_PLUS_FOLD_SAFE_ISOTONIC",
            })
    return output


def _profile(raw: list[dict[str, Any]]) -> dict[str, Any]:
    if not raw:
        raise ValueError("NFL_M2_V2H_PROFILE_EMPTY")
    totals = {key: 0.0 for key in _KEYS}
    for row in raw:
        payload = row["candidate_signed_key_probability"]
        for key in _KEYS:
            value = float(payload[str(key)])
            if not 0.0 <= value <= 1.0:
                raise ValueError("NFL_M2_V2H_KEY_PROBABILITY_INVALID")
            totals[key] += value
    n = float(len(raw))
    return {
        "contract": "NFL_M2_V2H_OOS_SIGNED_KEY_PMF_V1",
        "model_id": NFL_M2_V2H_CANDIDATE_MODEL_ID,
        "distribution_contract": NFL_M2_V2H_DISTRIBUTION_CONTRACT,
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "probability_source": "FIRST_OOS_PREREGISTERED_V2H_SCORING_SEQUENCE_DISTRIBUTION",
        "heldout_game_count": len(raw),
        "test_seasons": sorted({int(row["season"]) for row in raw}),
        "signed_key_probability": {str(key): totals[key] / n for key in _KEYS},
    }


def build_nfl_m2_v2h_candidate_evidence(
    rows: Iterable[dict[str, Any]],
    *,
    source_manifest_sha256: str,
    min_train_seasons: int = 2,
    min_calibration_fit_seasons: int = 2,
    calibration_bins: int = 10,
    calibration_min_bin_n: int = 25,
    calibration_threshold: float = 0.05,
    fold_win_threshold: float = 0.65,
    prior_drives: float = 48.0,
    max_events_per_type: int = 9,
) -> dict[str, Any]:
    manifest = str(source_manifest_sha256 or "").strip().lower()
    if len(manifest) != 64:
        raise ValueError("NFL_M2_V2H_SOURCE_MANIFEST_SHA256_INVALID")
    try:
        int(manifest, 16)
    except ValueError as exc:
        raise ValueError("NFL_M2_V2H_SOURCE_MANIFEST_SHA256_INVALID") from exc

    raw = build_nfl_m2_v2h_raw_evaluations(
        rows,
        min_train_seasons=min_train_seasons,
        prior_drives=prior_drives,
        max_events_per_type=max_events_per_type,
    )
    calibrated = calibrate_nfl_evaluations(raw, min_fit_seasons=min_calibration_fit_seasons)
    folds = _fold_rows(calibrated)
    calibration = build_calibration_evidence(
        calibrated,
        bins=calibration_bins,
        min_bin_n=calibration_min_bin_n,
        max_bin_deviation_threshold=calibration_threshold,
    )
    historical = {}
    for market in ("spread", "total"):
        market_folds = [row for row in folds if row["market"] == market]
        wins = sum(bool(row["candidate_beats_m1"]) for row in market_folds)
        rate = wins / len(market_folds) if market_folds else 0.0
        historical[market] = {
            "fold_wins": wins,
            "fold_total": len(market_folds),
            "fold_win_rate": rate,
            "required_fold_win_rate": float(fold_win_threshold),
            "historical_predictive_pass": bool(market_folds and rate >= float(fold_win_threshold)),
            "calibration": calibration.get(market),
        }

    return {
        "schema_version": 1,
        "status": "FIRST_READOUT_DIAGNOSTIC_ONLY",
        "preregistration_locked": True,
        "post_readout_retuning_allowed": False,
        "promotion_eligible": False,
        "promotion_authority": False,
        "model_p_authority": False,
        "official_status_granted": False,
        "production_registry_consumes_this_artifact": False,
        "model_id": NFL_M2_V2H_CANDIDATE_MODEL_ID,
        "distribution_contract": NFL_M2_V2H_DISTRIBUTION_CONTRACT,
        "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
        "source_manifest_sha256": manifest,
        "raw_evaluation_count": len(raw),
        "fold_count": len(folds),
        "folds": folds,
        "calibration_evidence": calibration,
        "candidate_distribution_profile": _profile(raw),
        "candidate_historical_evidence": historical,
        "parameters_frozen_before_readout": {
            "min_train_seasons": int(min_train_seasons),
            "min_calibration_fit_seasons": int(min_calibration_fit_seasons),
            "calibration_bins": int(calibration_bins),
            "calibration_min_bin_n": int(calibration_min_bin_n),
            "calibration_threshold": float(calibration_threshold),
            "fold_win_threshold": float(fold_win_threshold),
            "prior_drives": float(prior_drives),
            "max_events_per_type": int(max_events_per_type),
        },
    }
