"""Deterministic market-blind historical enrichment for CFB candidate transforms.

This module does not fit or score a model. It attaches the dual prior/current metric
snapshots and current-season games-in-sample counts required by the preregistered
candidate families. Inputs must already be historical/PIT-safe metric objects.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from .candidate_families import CFBCandidateFamilyError
from .source import CFBTeamMetrics


def _index(metrics: Iterable[CFBTeamMetrics]) -> dict[tuple[str, int, int, str], CFBTeamMetrics]:
    out: dict[tuple[str, int, int, str], CFBTeamMetrics] = {}
    for metric in metrics:
        if not isinstance(metric, CFBTeamMetrics):
            raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_METRIC_OBJECT_INVALID")
        key = (
            str(metric.team), int(metric.season), int(metric.through_week),
            str(metric.sample_source).upper(),
        )
        if key in out:
            raise CFBCandidateFamilyError(f"CFB_CANDIDATE_HISTORY_METRIC_DUPLICATE:{key}")
        out[key] = metric
    return out


def _prior(index, *, team: str, season: int) -> CFBTeamMetrics:
    rows = [
        metric for (name, metric_season, _week, source), metric in index.items()
        if name == team and metric_season == season - 1 and source == "PRIOR_SEASON_FALLBACK"
    ]
    if len(rows) != 1:
        raise CFBCandidateFamilyError(
            f"CFB_CANDIDATE_HISTORY_PRIOR_COUNT:{team}:{season}:{len(rows)}"
        )
    return rows[0]


def _current(index, *, team: str, season: int, week: int) -> CFBTeamMetrics:
    metric = index.get((team, season, week - 1, "CURRENT_SEASON_PRIOR_WEEKS"))
    if metric is None:
        raise CFBCandidateFamilyError(
            f"CFB_CANDIDATE_HISTORY_CURRENT_MISSING:{team}:{season}:{week-1}"
        )
    return metric


def enrich_candidate_history(
    rows: Iterable[Mapping[str, Any]],
    *,
    metrics: Iterable[CFBTeamMetrics],
) -> list[dict[str, Any]]:
    """Attach deterministic dual snapshots and counts to PIT-safe training rows.

    Games-in-sample is counted from earlier rows in the same season only. The
    function never reads realized score values to choose a source or weight.
    """
    data = [deepcopy(dict(row)) for row in rows]
    if not data:
        raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_EMPTY")
    index = _index(metrics)

    identities: list[tuple[int, int, str, str, str]] = []
    for row in data:
        try:
            season = int(row["season"])
            week = int(row["week"])
            game_id = str(row["game_id"])
            home = str(row["home_metrics"]["team"])
            away = str(row["away_metrics"]["team"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_IDENTITY_INVALID") from exc
        if week < 1 or not game_id or not home or not away:
            raise CFBCandidateFamilyError("CFB_CANDIDATE_HISTORY_IDENTITY_INVALID")
        identities.append((season, week, game_id, home, away))

    for row, (season, week, _game_id, home, away) in zip(data, identities):
        for side, team in (("home", home), ("away", away)):
            prior = _prior(index, team=team, season=season)
            row[f"{side}_prior_metrics"] = prior.to_dict()
            if week > 1:
                current = _current(index, team=team, season=season, week=week)
            else:
                current = prior
            current_dict = current.to_dict()
            games = sum(
                1
                for other_season, other_week, _gid, other_home, other_away in identities
                if other_season == season
                and other_week < week
                and team in {other_home, other_away}
            )
            current_dict["games_in_sample"] = games
            row[f"{side}_current_metrics"] = current_dict
    return data


__all__ = ["enrich_candidate_history"]
