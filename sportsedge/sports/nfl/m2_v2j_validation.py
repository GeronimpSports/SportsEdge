"""First frozen historical readout for preregistered research-only NFL V2J."""
from __future__ import annotations

from math import isfinite, log
from typing import Any, Iterable

import numpy as np

from sportsedge.core.walkforward.season import season_walk_forward
from .historical_validation import build_calibration_evidence, calibrate_nfl_evaluations, no_vig_two_way
from .m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT
from .m2_v2i_candidate import _combine_pmfs, _repeat_convolution, _safety_pmf, _safety_probability
from .m2_v2j_candidate import (
    NFL_M2_V2J_CANDIDATE_MODEL_ID,
    NFL_M2_V2J_DISTRIBUTION_CONTRACT,
    conditioned_drive_probabilities,
    fit_nfl_m2_v2j_candidate,
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


def _market_readout(model, row: dict[str, Any]) -> dict[str, Any]:
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
    spread_win = spread_push = total_win = total_push = total_weight = 0.0
    key_profile = {str(key): 0.0 for key in _KEYS}
    for env, env_weight in model.shared_environment:
        home_drive = conditioned_drive_probabilities(model, offense=home, defense=away, offense_features=hf, defense_features=af, shared_environment=env)
        away_drive = conditioned_drive_probabilities(model, offense=away, defense=home, offense_features=af, defense_features=hf, shared_environment=env)
        for home_drives, away_drives, regime_weight in base.possession_regime:
            home_scores = _combine_pmfs(_repeat_convolution(home_drive, home_drives), _safety_pmf(away_drives, home_safety_p))
            away_scores = _combine_pmfs(_repeat_convolution(away_drive, away_drives), _safety_pmf(home_drives, away_safety_p))
            home_values = np.fromiter(home_scores.keys(), dtype=np.int64)
            home_probs = np.fromiter(home_scores.values(), dtype=np.float64)
            away_values = np.fromiter(away_scores.keys(), dtype=np.int64)
            away_probs = np.fromiter(away_scores.values(), dtype=np.float64)
            weights = float(env_weight) * float(regime_weight) * np.outer(home_probs, away_probs)
            margins = home_values[:, None] - away_values[None, :]
            totals = home_values[:, None] + away_values[None, :]
            total_weight += float(weights.sum())
            for key in _KEYS:
                key_profile[str(key)] += float(weights[margins == key].sum())
            if spread_line is not None:
                spread_win += float(weights[margins > spread_line].sum())
                spread_push += float(weights[margins == spread_line].sum())
            if total_line is not None:
                total_win += float(weights[totals > total_line].sum())
                total_push += float(weights[totals == total_line].sum())
    if abs(total_weight - 1.0) > 1e-8:
        raise ValueError("NFL_M2_V2J_WEIGHT_CONSERVATION_FAILED")
    home_cover = None if spread_line is None or total_weight <= spread_push else _clip(spread_win / (total_weight - spread_push))
    over = None if total_line is None or total_weight <= total_push else _clip(total_win / (total_weight - total_push))
    return {"spread_line": spread_line, "total_line": total_line, "m2_home_cover_prob": home_cover, "m2_over_prob": over, "candidate_signed_key_probability": key_profile}


def build_nfl_m2_v2j_raw_evaluations(event_rows: Iterable[dict[str, Any]], feature_rows: Iterable[dict[str, Any]], *, min_train_seasons: int = 2) -> list[dict[str, Any]]:
    events = [dict(row) for row in event_rows]
    features = [dict(row) for row in feature_rows]
    by_game = {str(row.get("game_id") or ""): row for row in features}
    folds = season_walk_forward(features, season_key="season", min_train_seasons=min_train_seasons)
    output: list[dict[str, Any]] = []
    for fold in folds:
        train_seasons = {int(row["season"]) for row in fold.train_rows}
        train_events = [row for row in events if int(row["season"]) in train_seasons and str(row.get("game_id") or "") in by_game]
        model = fit_nfl_m2_v2j_candidate(train_events, fold.train_rows)
        for raw in fold.test_rows:
            row = dict(raw)
            readout = _market_readout(model, row)
            home_score = _float(row.get("home_score")); away_score = _float(row.get("away_score"))
            if home_score is None or away_score is None:
                raise ValueError("NFL_M2_V2J_REALIZED_SCORE_MISSING")
            margin = home_score - away_score; total = home_score + away_score
            spread_line = readout["spread_line"]; total_line = readout["total_line"]
            spread_push = spread_line is not None and margin == spread_line
            total_push = total_line is not None and total == total_line
            m1_home, _ = _novig(row.get("home_spread_odds"), row.get("away_spread_odds"))
            m1_over, _ = _novig(row.get("over_odds"), row.get("under_odds"))
            output.append({
                "game_id": str(row.get("game_id") or ""), "season": int(row["season"]), "week": row.get("week"),
                "model_id": model.model_id, "distribution_contract": model.distribution_contract, "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
                "spread_line": spread_line, "total_line": total_line, "spread_push": bool(spread_push), "total_push": bool(total_push),
                "home_cover_outcome": None if spread_line is None or spread_push else int(margin > spread_line),
                "over_outcome": None if total_line is None or total_push else int(total > total_line),
                "m1_home_cover_prob": m1_home, "m1_over_prob": m1_over,
                "m2_home_cover_prob": readout["m2_home_cover_prob"], "m2_over_prob": readout["m2_over_prob"],
                "candidate_signed_key_probability": readout["candidate_signed_key_probability"],
            })
    return output


def _loss(pairs):
    ll = brier = 0.0
    for outcome, probability in pairs:
        p = _clip(probability); ll += -(outcome * log(p) + (1-outcome)*log(1-p)); brier += (p-outcome)**2
    n = float(len(pairs)); return ll/n, brier/n


def _fold_rows(evaluations):
    specs = {"spread": ("home_cover_outcome", "m1_home_cover_prob", "m2_home_cover_calibrated_prob"), "total": ("over_outcome", "m1_over_prob", "m2_over_calibrated_prob")}
    out = []
    for season in sorted({int(row["season"]) for row in evaluations}):
        rows = [r for r in evaluations if int(r["season"]) == season]
        for market, (ok, bk, ck) in specs.items():
            eligible = [r for r in rows if r.get(ok) in (0,1) and r.get(ck) is not None]
            comparable = [r for r in eligible if r.get(bk) is not None]
            if not comparable: continue
            bll, bb = _loss([(int(r[ok]), float(r[bk])) for r in comparable]); cll, cb = _loss([(int(r[ok]), float(r[ck])) for r in comparable])
            out.append({"season": season, "market": market, "n": len(comparable), "eligible_n": len(eligible), "m1_coverage": len(comparable)/len(eligible), "m1_log_loss": bll, "candidate_log_loss": cll, "m1_brier": bb, "candidate_brier": cb, "candidate_beats_m1": cll < bll, "candidate_probability_source": "V2J_MARKET_BLIND_CONDITIONED_DRIVE_SHARED_ENV_PLUS_FOLD_SAFE_ISOTONIC"})
    return out


def _profile(raw):
    totals = {key: 0.0 for key in _KEYS}
    for row in raw:
        for key in _KEYS: totals[key] += float(row["candidate_signed_key_probability"][str(key)])
    n = float(len(raw))
    return {"contract": "NFL_M2_V2J_OOS_SIGNED_KEY_PMF_V1", "model_id": NFL_M2_V2J_CANDIDATE_MODEL_ID, "distribution_contract": NFL_M2_V2J_DISTRIBUTION_CONTRACT, "event_contract": NFL_M2_V2H_EVENT_CONTRACT, "probability_source": "FIRST_OOS_PREREGISTERED_V2J_CONDITIONED_DRIVE_SHARED_ENV_DISTRIBUTION", "heldout_game_count": len(raw), "test_seasons": sorted({int(r["season"]) for r in raw}), "signed_key_probability": {str(key): totals[key]/n for key in _KEYS}}


def build_nfl_m2_v2j_candidate_evidence(event_rows, feature_rows, *, source_manifest_sha256: str, min_train_seasons: int = 2, min_calibration_fit_seasons: int = 2, calibration_bins: int = 10, calibration_min_bin_n: int = 25, calibration_threshold: float = 0.05, fold_win_threshold: float = 0.65):
    manifest = str(source_manifest_sha256 or "").strip().lower()
    if len(manifest) != 64: raise ValueError("NFL_M2_V2J_SOURCE_MANIFEST_SHA256_INVALID")
    raw = build_nfl_m2_v2j_raw_evaluations(event_rows, feature_rows, min_train_seasons=min_train_seasons)
    calibrated = calibrate_nfl_evaluations(raw, min_fit_seasons=min_calibration_fit_seasons)
    folds = _fold_rows(calibrated)
    calibration = build_calibration_evidence(calibrated, bins=calibration_bins, min_bin_n=calibration_min_bin_n, max_bin_deviation_threshold=calibration_threshold)
    historical = {}
    for market in ("spread", "total"):
        mf = [r for r in folds if r["market"] == market]; wins = sum(bool(r["candidate_beats_m1"]) for r in mf); rate = wins/len(mf) if mf else 0.0
        historical[market] = {"fold_wins": wins, "fold_total": len(mf), "fold_win_rate": rate, "required_fold_win_rate": float(fold_win_threshold), "historical_predictive_pass": bool(mf and rate >= float(fold_win_threshold)), "calibration": calibration.get(market)}
    return {"schema_version": 1, "status": "FIRST_READOUT_DIAGNOSTIC_ONLY", "preregistration_locked": True, "post_readout_retuning_allowed": False, "promotion_eligible": False, "promotion_authority": False, "model_p_authority": False, "official_status_granted": False, "production_registry_consumes_this_artifact": False, "model_id": NFL_M2_V2J_CANDIDATE_MODEL_ID, "distribution_contract": NFL_M2_V2J_DISTRIBUTION_CONTRACT, "event_contract": NFL_M2_V2H_EVENT_CONTRACT, "source_manifest_sha256": manifest, "raw_evaluation_count": len(raw), "fold_count": len(folds), "folds": folds, "calibration_evidence": calibration, "candidate_distribution_profile": _profile(raw), "candidate_historical_evidence": historical, "parameters_frozen_before_readout": {"min_train_seasons": int(min_train_seasons), "min_calibration_fit_seasons": int(min_calibration_fit_seasons), "calibration_bins": int(calibration_bins), "calibration_min_bin_n": int(calibration_min_bin_n), "calibration_threshold": float(calibration_threshold), "fold_win_threshold": float(fold_win_threshold)}}
