"""Deterministic market-blind enrichment for the four frozen CFB candidate families.

The existing historical materializer remains the baseline PIT surface. This module
adds the prior/current snapshots and games-in-sample counts required by the three
non-baseline candidate families without reading market data or evaluation results.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from .candidate_families import CFBCandidateFamilyError
from .source import CFBTeamMetrics


def _metric_index(metrics: Iterable[CFBTeamMetrics]) -> dict[tuple[str, int, int, str], CFBTeamMetrics]:
    out: dict[tuple[str, int, int, str], CFBTeamMetrics] = {}
    for metric in metrics:
        key = (metric.team, int(metric.season), int(metric.through_week), str(metric.sample_source).upper())
        if key in out:
            raise CFBCandidateFamilyError(f"CFB_CANDIDATE_METRIC_DUPLICATE:{key}")
        out[key] = metric
    return out


def _prior(index: Mapping[tuple[str, int, int, str], CFBTeamMetrics], team: str, season: int) -> CFBTeamMetrics:
    found = [m for (t, s, _w, src), m in index.items() if t == team and s == season - 1 and src == "PRIOR_SEASON_FALLBACK"]
    if len(found) != 1:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_PRIOR_METRIC_COUNT:{team}:{season}:{len(found)}")
    return found[0]


def _current(index: Mapping[tuple[str, int, int, str], CFBTeamMetrics], team: str, season: int, week: int) -> CFBTeamMetrics:
    key = (team, season, week - 1, "CURRENT_SEASON_PRIOR_WEEKS")
    metric = index.get(key)
    if metric is None:
        raise CFBCandidateFamilyError(f"CFB_CANDIDATE_CURRENT_METRIC_MISSING:{team}:{season}:{week-1}")
    return metric


def enrich_candidate_history(rows: Iterable[Mapping[str, Any]], metrics: Iterable[CFBTeamMetrics]) -> list[dict[str, Any]]:
    """Add candidate-only source snapshots/counts to already materialized PIT rows."""
    data = [deepcopy(dict(row)) for row in rows]
    if not data:
        raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_EMPTY")
    index = _metric_index(metrics)

    identities: list[tuple[int, int, str, str, str]] = []
    for row in data:
        try:
            season, week = int(row["season"]), int(row["week"])
            game_id = str(row["game_id"])
            home = str(row["home_metrics"]["team"])
            away = str(row["away_metrics"]["team"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_IDENTITY_INVALID") from exc
        identities.append((season, week, game_id, home, away))

    for row, (season, week, _game_id, home, away) in zip(data, identities):
        for side, team in (("home", home), ("away", away)):
            prior = _prior(index, team, season)
            row[f"{side}_prior_metrics"] = prior.to_dict()
            if week > 1:
                row[f"{side}_current_metrics"] = _current(index, team, season, week).to_dict()
            games = sum(
                1 for s, w, _gid, h, a in identities
                if s == season and w < week and team in {h, a}
            )
            row[f"{side}_games_in_sample"] = games
    return data


__all__ = ["enrich_candidate_history"]
