"""NFL team-total derivatives from an already-built joint score distribution.

This module never fits a model and never consumes sportsbook information while
creating Model_P.  It prices home/away team totals only after the independent
joint score distribution exists.  Promotion is market-specific: a deployed game
total can never confer authority on either team-total derivative.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

TEAM_TOTAL_DERIVATIVE_CONTRACT = "NFL_TEAM_TOTAL_DERIVATIVE_V1"
SUPPORTED_TEAM_TOTALS = frozenset({"HOME_TEAM_TOTAL", "AWAY_TEAM_TOTAL"})


class NFLTeamTotalError(ValueError):
    pass


@dataclass(frozen=True)
class TeamTotalReadiness:
    contract: str
    market: str
    stage: str
    eligible: bool
    reason: str
    inherited_from_game_total: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _line(value: Any, reason: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise NFLTeamTotalError(reason) from exc
    if not isfinite(out) or out < 0:
        raise NFLTeamTotalError(reason)
    return out


def _score(row: Mapping[str, Any], field: str) -> float:
    if field not in row:
        raise NFLTeamTotalError(f"NFL_TEAM_TOTAL_SCORE_MISSING:{field}")
    value = _line(row[field], f"NFL_TEAM_TOTAL_SCORE_INVALID:{field}")
    return value


def _price(values: list[float], threshold: float) -> dict[str, float]:
    n = float(len(values))
    return {
        "over": sum(value > threshold for value in values) / n,
        "under": sum(value < threshold for value in values) / n,
        "push": sum(value == threshold for value in values) / n,
    }


def price_nfl_team_totals(
    distribution: Iterable[Mapping[str, Any]],
    *,
    home_total_line: float,
    away_total_line: float,
) -> dict[str, dict[str, float]]:
    """Price both team totals from the same market-blind joint score paths."""
    rows = [dict(row) for row in distribution]
    if not rows:
        raise NFLTeamTotalError("NFL_TEAM_TOTAL_SCORE_DISTRIBUTION_EMPTY")
    home_line = _line(home_total_line, "NFL_HOME_TEAM_TOTAL_LINE_INVALID")
    away_line = _line(away_total_line, "NFL_AWAY_TEAM_TOTAL_LINE_INVALID")
    home_scores = [_score(row, "home_score") for row in rows]
    away_scores = [_score(row, "away_score") for row in rows]
    return {
        "home_team_total": _price(home_scores, home_line),
        "away_team_total": _price(away_scores, away_line),
    }


def resolve_team_total_readiness(
    market: str,
    *,
    derivative_promotion_row: Mapping[str, Any] | None,
    game_total_promotion_row: Mapping[str, Any] | None = None,
) -> TeamTotalReadiness:
    """Resolve derivative authority without inheriting from game-total promotion.

    ``game_total_promotion_row`` is accepted only so callers can prove that parent
    deployment is irrelevant.  The derivative must carry its own internally
    consistent stage/eligible evidence.
    """
    resolved = str(market or "").strip().upper()
    if resolved not in SUPPORTED_TEAM_TOTALS:
        raise NFLTeamTotalError(f"NFL_TEAM_TOTAL_MARKET_UNSUPPORTED:{resolved}")

    # Deliberately do not inspect parent eligibility: no inheritance is allowed.
    _ = game_total_promotion_row
    if derivative_promotion_row is None:
        return TeamTotalReadiness(
            contract=TEAM_TOTAL_DERIVATIVE_CONTRACT,
            market=resolved,
            stage="EVIDENCE_BLOCKED",
            eligible=False,
            reason="TEAM_TOTAL_MARKET_SPECIFIC_PROMOTION_EVIDENCE_REQUIRED",
        )
    if not isinstance(derivative_promotion_row, Mapping):
        raise NFLTeamTotalError("NFL_TEAM_TOTAL_PROMOTION_ROW_INVALID")

    stage = str(derivative_promotion_row.get("stage") or "").strip().upper()
    eligible = derivative_promotion_row.get("eligible")
    if not stage:
        raise NFLTeamTotalError("NFL_TEAM_TOTAL_PROMOTION_STAGE_REQUIRED")
    if not isinstance(eligible, bool):
        raise NFLTeamTotalError("NFL_TEAM_TOTAL_PROMOTION_ELIGIBLE_INVALID")
    if eligible is not (stage == "DEPLOYED"):
        raise NFLTeamTotalError("NFL_TEAM_TOTAL_PROMOTION_STAGE_CONTRADICTION")

    return TeamTotalReadiness(
        contract=TEAM_TOTAL_DERIVATIVE_CONTRACT,
        market=resolved,
        stage=stage,
        eligible=eligible,
        reason=(
            "TEAM_TOTAL_MARKET_SPECIFIC_PROMOTION_PASS"
            if eligible
            else "TEAM_TOTAL_MARKET_SPECIFIC_PROMOTION_EVIDENCE_REQUIRED"
        ),
        inherited_from_game_total=False,
    )
