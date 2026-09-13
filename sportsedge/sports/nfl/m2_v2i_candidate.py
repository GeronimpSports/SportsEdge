"""Research-only NFL V2I shared-game-regime candidate.

V2I is preregistered in
``config/research/nfl_v2i_shared_game_regime_prereg_2026-09-12.json``.
It has no production Model_P, promotion, staking, OFFICIAL, market-eligibility,
or registry authority. Sportsbook prices are not model inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb, isfinite, sqrt
from typing import Any, Iterable, Mapping

from sportsedge.sports.nfl.m2_v2h_candidate import NFL_M2_V2H_EVENT_CONTRACT

NFL_M2_V2I_CANDIDATE_MODEL_ID = "nfl_v2i_shared_game_regime_candidate"
NFL_M2_V2I_DISTRIBUTION_CONTRACT = "NFL_M2_V2I_SHARED_GAME_REGIME_V1"

_MARKET_FIELDS = {
    "spread_line", "total_line", "moneyline", "home_moneyline", "away_moneyline",
    "home_spread_odds", "away_spread_odds", "over_odds", "under_odds",
    "closing_spread", "closing_total",
}
_OFFENSE_EVENT_POINTS = {
    "td_xp_good": 7,
    "td_xp_miss": 6,
    "td_two_good": 8,
    "td_two_fail": 6,
    "field_goals": 3,
}


def _float(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _int(value: Any) -> int | None:
    parsed = _float(value)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


@dataclass(frozen=True)
class NFLV2ITeamState:
    games: int
    drives: int
    drives_faced: int
    td_xp_good: int
    td_xp_miss: int
    td_two_good: int
    td_two_fail: int
    field_goals: int
    td_xp_good_allowed: int
    td_xp_miss_allowed: int
    td_two_good_allowed: int
    td_two_fail_allowed: int
    field_goals_allowed: int
    safeties_scored: int
    safeties_allowed: int


@dataclass(frozen=True)
class NFLM2V2ICandidateModel:
    model_id: str
    distribution_contract: str
    train_seasons: tuple[int, ...]
    possession_regime: tuple[tuple[int, int, float], ...]
    league_offense_rates: Mapping[str, float]
    league_safety_rate: float
    team_state: Mapping[str, NFLV2ITeamState]
    prior_drives: float


def _validate_row(row: Mapping[str, Any]) -> tuple[str, str, int, dict[str, int]]:
    if str(row.get("event_contract") or "") != NFL_M2_V2H_EVENT_CONTRACT:
        raise ValueError("NFL_M2_V2I_EVENT_CONTRACT_INVALID")
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    season = _int(row.get("season"))
    if not home or not away or home == away or season is None:
        raise ValueError("NFL_M2_V2I_TRAINING_IDENTITY_INVALID")
    counts: dict[str, int] = {}
    for side in ("home", "away"):
        drives = _int(row.get(f"{side}_drives"))
        no_score = _int(row.get(f"{side}_other_no_score"))
        safety = _int(row.get(f"{side}_safeties"))
        if drives is None or no_score is None or safety is None or drives <= 0 or no_score < 0 or safety < 0:
            raise ValueError("NFL_M2_V2I_EVENT_COUNT_INVALID")
        counts[f"{side}_drives"] = drives
        counts[f"{side}_other_no_score"] = no_score
        counts[f"{side}_safeties"] = safety
        scoring = 0
        for key in _OFFENSE_EVENT_POINTS:
            value = _int(row.get(f"{side}_{key}"))
            if value is None or value < 0:
                raise ValueError("NFL_M2_V2I_EVENT_COUNT_INVALID")
            counts[f"{side}_{key}"] = value
            scoring += value
        if scoring + no_score != drives:
            raise ValueError("NFL_M2_V2I_DRIVE_PARTITION_INVALID")
    return home, away, season, counts


def fit_nfl_m2_v2i_candidate(
    rows: Iterable[Mapping[str, Any]],
    *,
    prior_drives: float = 48.0,
) -> NFLM2V2ICandidateModel:
    data = [dict(row) for row in rows]
    if len(data) < 2:
        raise ValueError("NFL_M2_V2I_TRAINING_ROWS_INSUFFICIENT")
    if not isfinite(float(prior_drives)) or float(prior_drives) <= 0:
        raise ValueError("NFL_M2_V2I_PARAMETER_INVALID")

    mutable: dict[str, dict[str, int]] = {}
    regime_counts: dict[tuple[int, int], int] = {}
    league = {key: 0 for key in _OFFENSE_EVENT_POINTS}
    league_drives = 0
    league_safeties = 0
    league_drives_faced = 0
    seasons: set[int] = set()

    def blank() -> dict[str, int]:
        return {
            "games": 0,
            "drives": 0,
            "drives_faced": 0,
            "safeties_scored": 0,
            "safeties_allowed": 0,
            **{key: 0 for key in _OFFENSE_EVENT_POINTS},
            **{f"{key}_allowed": 0 for key in _OFFENSE_EVENT_POINTS},
        }

    for row in data:
        home, away, season, counts = _validate_row(row)
        seasons.add(season)
        home_drives = counts["home_drives"]
        away_drives = counts["away_drives"]
        regime_counts[(home_drives, away_drives)] = regime_counts.get((home_drives, away_drives), 0) + 1
        for side, team, opponent, opp_side in (
            ("home", home, away, "away"),
            ("away", away, home, "home"),
        ):
            own = mutable.setdefault(team, blank())
            opp = mutable.setdefault(opponent, blank())
            drives = counts[f"{side}_drives"]
            opponent_drives = counts[f"{opp_side}_drives"]
            own["games"] += 1
            own["drives"] += drives
            own["drives_faced"] += opponent_drives
            league_drives += drives
            league_drives_faced += opponent_drives
            for key in _OFFENSE_EVENT_POINTS:
                value = counts[f"{side}_{key}"]
                own[key] += value
                opp[f"{key}_allowed"] += value
                league[key] += value
            safeties_scored = counts[f"{side}_safeties"]
            safeties_allowed = counts[f"{opp_side}_safeties"]
            own["safeties_scored"] += safeties_scored
            own["safeties_allowed"] += safeties_allowed
            league_safeties += safeties_scored

    if league_drives <= 0 or league_drives_faced <= 0 or not regime_counts:
        raise ValueError("NFL_M2_V2I_LEAGUE_STATE_EMPTY")

    league_rates = {key: league[key] / float(league_drives) for key in _OFFENSE_EVENT_POINTS}
    league_safety_rate = league_safeties / float(league_drives_faced)
    total_regimes = float(sum(regime_counts.values()))
    possession_regime = tuple(
        (home_drives, away_drives, count / total_regimes)
        for (home_drives, away_drives), count in sorted(regime_counts.items())
    )
    states: dict[str, NFLV2ITeamState] = {}
    for team, value in sorted(mutable.items()):
        states[team] = NFLV2ITeamState(
            games=value["games"],
            drives=value["drives"],
            drives_faced=value["drives_faced"],
            td_xp_good=value["td_xp_good"],
            td_xp_miss=value["td_xp_miss"],
            td_two_good=value["td_two_good"],
            td_two_fail=value["td_two_fail"],
            field_goals=value["field_goals"],
            td_xp_good_allowed=value["td_xp_good_allowed"],
            td_xp_miss_allowed=value["td_xp_miss_allowed"],
            td_two_good_allowed=value["td_two_good_allowed"],
            td_two_fail_allowed=value["td_two_fail_allowed"],
            field_goals_allowed=value["field_goals_allowed"],
            safeties_scored=value["safeties_scored"],
            safeties_allowed=value["safeties_allowed"],
        )

    return NFLM2V2ICandidateModel(
        model_id=NFL_M2_V2I_CANDIDATE_MODEL_ID,
        distribution_contract=NFL_M2_V2I_DISTRIBUTION_CONTRACT,
        train_seasons=tuple(sorted(seasons)),
        possession_regime=possession_regime,
        league_offense_rates=league_rates,
        league_safety_rate=league_safety_rate,
        team_state=states,
        prior_drives=float(prior_drives),
    )


def _smoothed_rate(events: int, opportunities: int, league: float, prior: float) -> float:
    return (events + prior * league) / (opportunities + prior)


def _offense_drive_probabilities(
    model: NFLM2V2ICandidateModel,
    offense: str,
    defense: str,
) -> dict[int, float]:
    off = model.team_state.get(offense)
    deff = model.team_state.get(defense)
    if off is None or deff is None:
        raise ValueError(f"NFL_M2_V2I_TEAM_STATE_MISSING:{offense}:{defense}")
    point_probs: dict[int, float] = {0: 0.0}
    scoring_total = 0.0
    for key, points in _OFFENSE_EVENT_POINTS.items():
        league = float(model.league_offense_rates[key])
        own = _smoothed_rate(getattr(off, key), off.drives, league, model.prior_drives)
        allowed = _smoothed_rate(getattr(deff, f"{key}_allowed"), deff.drives_faced, league, model.prior_drives)
        probability = max(0.0, sqrt(own * allowed))
        point_probs[points] = point_probs.get(points, 0.0) + probability
        scoring_total += probability
    if scoring_total >= 1.0:
        scale = 0.999999 / scoring_total
        for points in tuple(point_probs):
            if points != 0:
                point_probs[points] *= scale
        scoring_total = sum(value for points, value in point_probs.items() if points != 0)
    point_probs[0] = 1.0 - scoring_total
    total = sum(point_probs.values())
    return {points: probability / total for points, probability in sorted(point_probs.items())}


def _safety_probability(
    model: NFLM2V2ICandidateModel,
    defense: str,
    offense: str,
) -> float:
    deff = model.team_state.get(defense)
    off = model.team_state.get(offense)
    if deff is None or off is None:
        raise ValueError(f"NFL_M2_V2I_TEAM_STATE_MISSING:{defense}:{offense}")
    league = float(model.league_safety_rate)
    scored = _smoothed_rate(deff.safeties_scored, deff.drives_faced, league, model.prior_drives)
    allowed = _smoothed_rate(off.safeties_allowed, off.drives, league, model.prior_drives)
    return max(0.0, min(0.20, sqrt(scored * allowed)))


def _repeat_convolution(base: Mapping[int, float], count: int) -> dict[int, float]:
    if count < 0:
        raise ValueError("NFL_M2_V2I_NEGATIVE_POSSESSION_COUNT")
    pmf: dict[int, float] = {0: 1.0}
    for _ in range(count):
        nxt: dict[int, float] = {}
        for prior_score, prior_prob in pmf.items():
            for points, probability in base.items():
                score = prior_score + int(points)
                nxt[score] = nxt.get(score, 0.0) + prior_prob * float(probability)
        pmf = nxt
    return pmf


def _safety_pmf(opponent_drives: int, probability: float) -> dict[int, float]:
    if opponent_drives < 0 or probability < 0 or probability > 1 or not isfinite(probability):
        raise ValueError("NFL_M2_V2I_SAFETY_PARAMETER_INVALID")
    return {
        2 * k: comb(opponent_drives, k) * probability ** k * (1.0 - probability) ** (opponent_drives - k)
        for k in range(opponent_drives + 1)
    }


def _combine_pmfs(left: Mapping[int, float], right: Mapping[int, float]) -> dict[int, float]:
    combined: dict[int, float] = {}
    for left_score, left_prob in left.items():
        for right_score, right_prob in right.items():
            score = int(left_score) + int(right_score)
            combined[score] = combined.get(score, 0.0) + float(left_prob) * float(right_prob)
    return combined


def derive_nfl_m2_v2i_score_distribution(
    model: NFLM2V2ICandidateModel,
    row: Mapping[str, Any],
) -> tuple[dict[str, float | int], ...]:
    if model.model_id != NFL_M2_V2I_CANDIDATE_MODEL_ID or model.distribution_contract != NFL_M2_V2I_DISTRIBUTION_CONTRACT:
        raise ValueError("NFL_M2_V2I_MODEL_IDENTITY_INVALID")
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    if not home or not away or home == away:
        raise ValueError("NFL_M2_V2I_PREDICTION_IDENTITY_INVALID")
    _ = tuple(field for field in _MARKET_FIELDS if field in row)

    home_drive = _offense_drive_probabilities(model, home, away)
    away_drive = _offense_drive_probabilities(model, away, home)
    home_safety_p = _safety_probability(model, home, away)
    away_safety_p = _safety_probability(model, away, home)

    joint: dict[tuple[int, int], float] = {}
    for home_drives, away_drives, regime_weight in model.possession_regime:
        home_offense = _repeat_convolution(home_drive, home_drives)
        away_offense = _repeat_convolution(away_drive, away_drives)
        home_scores = _combine_pmfs(home_offense, _safety_pmf(away_drives, home_safety_p))
        away_scores = _combine_pmfs(away_offense, _safety_pmf(home_drives, away_safety_p))
        for home_score, home_prob in home_scores.items():
            for away_score, away_prob in away_scores.items():
                key = (int(home_score), int(away_score))
                joint[key] = joint.get(key, 0.0) + float(regime_weight) * float(home_prob) * float(away_prob)

    total_weight = sum(joint.values())
    if total_weight <= 0 or not isfinite(total_weight):
        raise ValueError("NFL_M2_V2I_WEIGHT_NORMALIZATION_FAILED")
    distribution = tuple(
        {
            "home_score": home_score,
            "away_score": away_score,
            "margin": home_score - away_score,
            "total": home_score + away_score,
            "weight": weight / total_weight,
        }
        for (home_score, away_score), weight in sorted(joint.items())
    )
    if abs(sum(float(item["weight"]) for item in distribution) - 1.0) > 1e-10:
        raise ValueError("NFL_M2_V2I_WEIGHT_CONSERVATION_FAILED")
    return distribution
