"""Exact, zero-authority sharding primitives for a possible V2J timeout successor.

This module exists only to make the preregistered first historical readout fit
within hosted-runner wall-clock limits without changing candidate mathematics.
It partitions *held-out rows*, not model inputs or probability calculations.
Every shard refits the identical frozen fold model, evaluates deterministic row
indices with ``market_readout_exact_cached``, and records enough identity to
fail closed during merge.  Calibration and predictive adjudication happen only
after a complete merge.

No workflow imports this module on ``main`` at creation time.  It grants no
Model_P, promotion, staking, RUN IT, OFFICIAL, or successor-readout authority.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from sportsedge.core.walkforward.season import season_walk_forward
from .historical_validation import build_calibration_evidence, calibrate_nfl_evaluations
from .m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from .m2_v2j_candidate import (
    NFL_M2_V2J_CANDIDATE_MODEL_ID,
    NFL_M2_V2J_DISTRIBUTION_CONTRACT,
    fit_nfl_m2_v2j_candidate,
)
from .m2_v2j_runtime_cache import market_readout_exact_cached
from .m2_v2j_validation import _float, _fold_rows, _novig, _profile

SHARD_CONTRACT = "NFL_M2_V2J_EXACT_HELDOUT_SHARD_V1"


class NFLV2JShardError(ValueError):
    pass


def _sha(value: Any, *, length: int, label: str) -> str:
    text = str(value or "").strip().lower()
    if len(text) != length or any(ch not in "0123456789abcdef" for ch in text):
        raise NFLV2JShardError(f"NFL_V2J_SHARD_{label}_INVALID")
    return text


def _evaluate_one(model: Any, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Mirror frozen ``build_nfl_m2_v2j_raw_evaluations`` row construction."""
    row = dict(raw)
    readout = market_readout_exact_cached(model, row)
    home_score = _float(row.get("home_score"))
    away_score = _float(row.get("away_score"))
    if home_score is None or away_score is None:
        raise NFLV2JShardError("NFL_M2_V2J_REALIZED_SCORE_MISSING")
    margin = home_score - away_score
    total = home_score + away_score
    spread_line = readout["spread_line"]
    total_line = readout["total_line"]
    spread_push = spread_line is not None and margin == spread_line
    total_push = total_line is not None and total == total_line
    m1_home, _ = _novig(row.get("home_spread_odds"), row.get("away_spread_odds"))
    m1_over, _ = _novig(row.get("over_odds"), row.get("under_odds"))
    return {
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
        "home_cover_outcome": None if spread_line is None or spread_push else int(margin > spread_line),
        "over_outcome": None if total_line is None or total_push else int(total > total_line),
        "m1_home_cover_prob": m1_home,
        "m1_over_prob": m1_over,
        "m2_home_cover_prob": readout["m2_home_cover_prob"],
        "m2_over_prob": readout["m2_over_prob"],
        "candidate_signed_key_probability": readout["candidate_signed_key_probability"],
    }


def build_v2j_raw_evaluation_shard(
    event_rows: Iterable[Mapping[str, Any]],
    feature_rows: Iterable[Mapping[str, Any]],
    *,
    test_season: int,
    shard_index: int,
    shard_count: int,
    source_manifest_sha256: str,
    code_git_sha: str,
    min_train_seasons: int = 2,
) -> dict[str, Any]:
    """Build one deterministic subset of one walk-forward test season."""
    manifest = _sha(source_manifest_sha256, length=64, label="SOURCE_MANIFEST_SHA256")
    code_sha = _sha(code_git_sha, length=40, label="CODE_GIT_SHA")
    if shard_count <= 0 or shard_index < 0 or shard_index >= shard_count:
        raise NFLV2JShardError("NFL_V2J_SHARD_GEOMETRY_INVALID")
    events = [dict(row) for row in event_rows]
    features = [dict(row) for row in feature_rows]
    by_game = {str(row.get("game_id") or ""): row for row in features}
    folds = season_walk_forward(features, season_key="season", min_train_seasons=min_train_seasons)
    chosen = None
    for fold in folds:
        seasons = sorted({int(row["season"]) for row in fold.test_rows})
        if seasons == [int(test_season)]:
            if chosen is not None:
                raise NFLV2JShardError("NFL_V2J_SHARD_TEST_SEASON_AMBIGUOUS")
            chosen = fold
    if chosen is None:
        raise NFLV2JShardError("NFL_V2J_SHARD_TEST_SEASON_NOT_FOUND")

    train_seasons = {int(row["season"]) for row in chosen.train_rows}
    train_events = [
        row for row in events
        if int(row["season"]) in train_seasons and str(row.get("game_id") or "") in by_game
    ]
    model = fit_nfl_m2_v2j_candidate(train_events, chosen.train_rows)
    rows: list[dict[str, Any]] = []
    for test_index, raw in enumerate(chosen.test_rows):
        if test_index % shard_count != shard_index:
            continue
        rows.append({
            "test_index": test_index,
            "evaluation": _evaluate_one(model, raw),
        })
    return {
        "contract": SHARD_CONTRACT,
        "status": "SHARD_COMPLETE_ZERO_AUTHORITY",
        "code_git_sha": code_sha,
        "source_manifest_sha256": manifest,
        "test_season": int(test_season),
        "train_seasons": sorted(train_seasons),
        "shard_index": int(shard_index),
        "shard_count": int(shard_count),
        "test_row_count": len(chosen.test_rows),
        "rows": rows,
        "predictive_verdict": None,
        "model_p_authority": False,
        "promotion_authority": False,
        "staking_authority": False,
        "official_authority": False,
    }


def merge_v2j_raw_evaluation_shards(shards: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge only a complete, identity-consistent shard set in frozen fold order."""
    data = [dict(item) for item in shards]
    if not data:
        raise NFLV2JShardError("NFL_V2J_SHARDS_EMPTY")
    manifests = {str(item.get("source_manifest_sha256") or "").lower() for item in data}
    code_shas = {str(item.get("code_git_sha") or "").lower() for item in data}
    if len(manifests) != 1 or len(code_shas) != 1:
        raise NFLV2JShardError("NFL_V2J_SHARD_IDENTITY_DRIFT")
    _sha(next(iter(manifests)), length=64, label="SOURCE_MANIFEST_SHA256")
    _sha(next(iter(code_shas)), length=40, label="CODE_GIT_SHA")

    by_season: dict[int, list[dict[str, Any]]] = {}
    for item in data:
        if item.get("contract") != SHARD_CONTRACT or item.get("status") != "SHARD_COMPLETE_ZERO_AUTHORITY":
            raise NFLV2JShardError("NFL_V2J_SHARD_CONTRACT_INVALID")
        for field in ("model_p_authority", "promotion_authority", "staking_authority", "official_authority"):
            if item.get(field) is not False:
                raise NFLV2JShardError(f"NFL_V2J_SHARD_FORBIDDEN_AUTHORITY:{field}")
        season = int(item["test_season"])
        by_season.setdefault(season, []).append(item)

    merged: list[dict[str, Any]] = []
    for season in sorted(by_season):
        group = by_season[season]
        shard_counts = {int(item["shard_count"]) for item in group}
        row_counts = {int(item["test_row_count"]) for item in group}
        train_sets = {tuple(int(x) for x in item.get("train_seasons") or []) for item in group}
        if len(shard_counts) != 1 or len(row_counts) != 1 or len(train_sets) != 1:
            raise NFLV2JShardError(f"NFL_V2J_SHARD_GEOMETRY_DRIFT:{season}")
        shard_count = next(iter(shard_counts))
        expected_indices = set(range(shard_count))
        observed_indices = {int(item["shard_index"]) for item in group}
        if observed_indices != expected_indices or len(group) != shard_count:
            raise NFLV2JShardError(f"NFL_V2J_SHARD_SET_INCOMPLETE:{season}")
        row_count = next(iter(row_counts))
        indexed: dict[int, dict[str, Any]] = {}
        for item in group:
            for wrapped in item.get("rows") or []:
                index = int(wrapped["test_index"])
                if index in indexed:
                    raise NFLV2JShardError(f"NFL_V2J_SHARD_DUPLICATE_TEST_INDEX:{season}:{index}")
                indexed[index] = dict(wrapped["evaluation"])
        if set(indexed) != set(range(row_count)):
            raise NFLV2JShardError(f"NFL_V2J_SHARD_ROW_COVERAGE_INCOMPLETE:{season}")
        merged.extend(indexed[index] for index in range(row_count))
    return merged


def build_v2j_candidate_evidence_from_raw_exact(
    raw_evaluations: Iterable[Mapping[str, Any]],
    *,
    source_manifest_sha256: str,
    min_calibration_fit_seasons: int = 2,
    calibration_bins: int = 10,
    calibration_min_bin_n: int = 25,
    calibration_threshold: float = 0.05,
    fold_win_threshold: float = 0.65,
    min_train_seasons: int = 2,
) -> dict[str, Any]:
    """Apply the unchanged post-readout evidence math to a complete raw merge."""
    manifest = _sha(source_manifest_sha256, length=64, label="SOURCE_MANIFEST_SHA256")
    raw = [dict(row) for row in raw_evaluations]
    calibrated = calibrate_nfl_evaluations(raw, min_fit_seasons=min_calibration_fit_seasons)
    folds = _fold_rows(calibrated)
    calibration = build_calibration_evidence(
        calibrated,
        bins=calibration_bins,
        min_bin_n=calibration_min_bin_n,
        max_bin_deviation_threshold=calibration_threshold,
    )
    historical: dict[str, Any] = {}
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
