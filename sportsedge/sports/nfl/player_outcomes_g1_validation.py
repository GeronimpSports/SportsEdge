"""Chronological validation for NFL player outcome engine G1.

Research-only. No market prices are consumed and no runtime authority is granted.
"""
from __future__ import annotations

from math import log, sqrt
from statistics import mean
from typing import Any, Iterable

from .player_outcomes_g1 import fit_count_distribution

_EPS = 1e-9


def _clip(p: float) -> float:
    return min(1.0 - _EPS, max(_EPS, float(p)))


def probability_metrics(pairs: Iterable[tuple[int, float]]) -> dict[str, float]:
    rows = [(int(y), _clip(float(p))) for y, p in pairs]
    if not rows:
        raise ValueError("NFL_PROP_G1_EMPTY_PROBABILITY_EVAL")
    brier = mean((p - y) ** 2 for y, p in rows)
    log_loss = mean(-(y * log(p) + (1 - y) * log(1 - p)) for y, p in rows)
    return {"n": len(rows), "brier": brier, "log_loss": log_loss}


def quantity_metrics(actual_pred: Iterable[tuple[float, float]]) -> dict[str, float]:
    rows = [(float(a), float(p)) for a, p in actual_pred]
    if not rows:
        raise ValueError("NFL_PROP_G1_EMPTY_QUANTITY_EVAL")
    errors = [p - a for a, p in rows]
    return {
        "n": len(rows),
        "mae": mean(abs(e) for e in errors),
        "rmse": sqrt(mean(e * e for e in errors)),
    }


def chronological_receptions_readout(
    rows: Iterable[dict[str, Any]],
    *,
    line: float = 4.5,
    min_prior_games: int = 5,
) -> dict[str, Any]:
    """Walk forward one player at a time using only prior games.

    Rows must include player_id, season, week, receptions. Each prediction uses
    only rows with an earlier (season, week) for the same player.
    """
    data = [dict(r) for r in rows]
    data.sort(key=lambda r: (int(r["season"]), int(r["week"]), str(r.get("player_id") or "")))
    history: dict[str, list[dict[str, Any]]] = {}
    probability_rows: list[tuple[int, float]] = []
    quantity_rows: list[tuple[float, float]] = []
    predictions: list[dict[str, Any]] = []

    for row in data:
        player_id = str(row.get("player_id") or "").strip()
        if not player_id:
            raise ValueError("NFL_PROP_G1_PLAYER_ID_REQUIRED")
        prior = history.setdefault(player_id, [])
        current = float(row.get("receptions") or 0.0)
        if len(prior) >= min_prior_games:
            values = [float(r.get("receptions") or 0.0) for r in prior]
            dist = fit_count_distribution(values)
            p_over = dist.prob_over_count_line(line)
            outcome = int(current > line)
            probability_rows.append((outcome, p_over))
            quantity_rows.append((current, dist.mean))
            predictions.append({
                "player_id": player_id,
                "season": int(row["season"]),
                "week": int(row["week"]),
                "line": float(line),
                "actual_receptions": current,
                "predicted_mean": dist.mean,
                "prob_over": p_over,
                "distribution_family": dist.family,
                "prior_game_count": len(prior),
            })
        prior.append(row)

    return {
        "schema": "SPORTSEDGE_NFL_PLAYER_OUTCOME_G1_RECEPTIONS_READOUT_V1",
        "status": "RESEARCH_ONLY",
        "market_prices_consumed": False,
        "random_split_used": False,
        "probability_metrics": probability_metrics(probability_rows),
        "quantity_metrics": quantity_metrics(quantity_rows),
        "predictions": predictions,
    }
