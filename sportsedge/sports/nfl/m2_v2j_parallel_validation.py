"""Unactivated exact ordered-parallel evidence adapter for NFL V2J.

This module is a runtime-only contingency for the timed-out preregistered V2J
historical readout. It preserves the frozen walk-forward folds, fold-model fitting,
per-game arithmetic, evaluation-row order, calibration logic, and evidence schema.
Only independent held-out game readouts within a fitted fold may run concurrently.

Nothing in this module grants rerun, predictive, Model_P, promotion, RUN IT,
staking, OFFICIAL, V2K, or successor-readout authority.
"""
from __future__ import annotations

from typing import Any, Iterable

from sportsedge.core.walkforward.season import season_walk_forward
from .historical_validation import build_calibration_evidence, calibrate_nfl_evaluations
from .m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from .m2_v2j_candidate import (
    NFL_M2_V2J_CANDIDATE_MODEL_ID,
    NFL_M2_V2J_DISTRIBUTION_CONTRACT,
    fit_nfl_m2_v2j_candidate,
)
from .m2_v2j_ordered_parallel import ordered_parallel_market_readouts_exact_cached
from .m2_v2j_validation import _float, _fold_rows, _novig, _profile


def build_nfl_m2_v2j_parallel_raw_evaluations(
    event_rows: Iterable[dict[str, Any]],
    feature_rows: Iterable[dict[str, Any]],
    *,
    max_workers: int,
    min_train_seasons: int = 2,
) -> list[dict[str, Any]]:
    """Build the frozen raw rows with ordered per-game process parallelism."""
    events = [dict(row) for row in event_rows]
    features = [dict(row) for row in feature_rows]
    by_game = {str(row.get("game_id") or ""): row for row in features}
    folds = season_walk_forward(features, season_key="season", min_train_seasons=min_train_seasons)
    output: list[dict[str, Any]] = []

    for fold in folds:
        train_seasons = {int(row["season"]) for row in fold.train_rows}
        train_events = [
            row
            for row in events
            if int(row["season"]) in train_seasons and str(row.get("game_id") or "") in by_game
        ]
        model = fit_nfl_m2_v2j_candidate(train_events, fold.train_rows)
        ordered_rows = tuple(dict(raw) for raw in fold.test_rows)
        readouts = ordered_parallel_market_readouts_exact_cached(
            model,
            ordered_rows,
            max_workers=max_workers,
        )
        if len(readouts) != len(ordered_rows):
            raise ValueError("NFL_M2_V2J_PARALLEL_READOUT_COUNT_MISMATCH")

        for row, readout in zip(ordered_rows, readouts):
            home_score = _float(row.get("home_score"))
            away_score = _float(row.get("away_score"))
            if home_score is None or away_score is None:
                raise ValueError("NFL_M2_V2J_REALIZED_SCORE_MISSING")
            margin = home_score - away_score
            total = home_score + away_score
            spread_line = readout["spread_line"]
            total_line = readout["total_line"]
            spread_push = spread_line is not None and margin == spread_line
            total_push = total_line is not None and total == total_line
            m1_home, _ = _novig(row.get("home_spread_odds"), row.get("away_spread_odds"))
            m1_over, _ = _novig(row.get("over_odds"), row.get("under_odds"))
            output.append(
                {
                    "game_id": str(row.get("game_id") or ""),
                    "season": int(row["season"]),
                    "week": row.get("week"),
                    "model_id": model.model_id,
                    "distribution_contract": model.distribution_contract,
                    "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
                    "spread_line": spread_line,
                    "total_line": total_line,
                    "spread_push": bool(spread_push),
                    "total_push": bool(total_push),
                    "home_cover_outcome": None
                    if spread_line is None or spread_push
                    else int(margin > spread_line),
                    "over_outcome": None
                    if total_line is None or total_push
                    else int(total > total_line),
                    "m1_home_cover_prob": m1_home,
                    "m1_over_prob": m1_over,
                    "m2_home_cover_prob": readout["m2_home_cover_prob"],
                    "m2_over_prob": readout["m2_over_prob"],
                    "candidate_signed_key_probability": readout["candidate_signed_key_probability"],
                }
            )
    return output


def build_nfl_m2_v2j_parallel_candidate_evidence(
    event_rows,
    feature_rows,
    *,
    source_manifest_sha256: str,
    max_workers: int,
    min_train_seasons: int = 2,
    min_calibration_fit_seasons: int = 2,
    calibration_bins: int = 10,
    calibration_min_bin_n: int = 25,
    calibration_threshold: float = 0.05,
    fold_win_threshold: float = 0.65,
):
    """Return the same evidence schema as the frozen serial builder."""
    manifest = str(source_manifest_sha256 or "").strip().lower()
    if len(manifest) != 64:
        raise ValueError("NFL_M2_V2J_SOURCE_MANIFEST_SHA256_INVALID")

    raw = build_nfl_m2_v2j_parallel_raw_evaluations(
        event_rows,
        feature_rows,
        max_workers=max_workers,
        min_train_seasons=min_train_seasons,
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
            "historical_predictive_pass": bool(
                market_folds and rate >= float(fold_win_threshold)
            ),
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
        "model_id": NFL_M2_V2J_CANDIDATE_MODEL_ID,
        "distribution_contract": NFL_M2_V2J_DISTRIBUTION_CONTRACT,
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
        },
    }
