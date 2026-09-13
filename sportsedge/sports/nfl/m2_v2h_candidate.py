"""Research-only NFL V2H football-native scoring-sequence candidate.

Implementation follows the preregistration frozen in
``config/research/nfl_v2h_scoring_sequence_model_prereg_2026-09-12.json``.
It is market blind and has no production Model_P, promotion, staking, OFFICIAL,
or registry authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial, isfinite, sqrt
from typing import Any, Iterable, Mapping

NFL_M2_V2H_CANDIDATE_MODEL_ID = "nfl_v2h_scoring_sequence_model_candidate"
NFL_M2_V2H_DISTRIBUTION_CONTRACT = "NFL_M2_V2H_FOOTBALL_SCORING_SEQUENCE_V1"
NFL_M2_V2H_EVENT_CONTRACT = "NFL_M2_V2H_POSSESSION_SCORING_SEQUENCE_ROWS_V1"

_MARKET_FIELDS = {
    "spread_line", "total_line", "moneyline", "home_moneyline", "away_moneyline",
    "home_spread_odds", "away_spread_odds", "over_odds", "under_odds",
    "closing_spread", "closing_total",
}
_EVENT_POINTS = {
    "td_xp_good": 7,
    "td_xp_miss": 6,
    "td_two_good": 8,
    "td_two_fail": 6,
    "field_goal": 3,
    "safety": 2,
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
    value = _float(value)
    if value is None or not value.is_integer():
        return None
    return int(value)


def _one(value: Any) -> bool:
    value = _float(value)
    return value is not None and value == 1.0


def _clamp(value: float, ceiling: float) -> float:
    return max(1e-8, min(float(ceiling), float(value)))


@dataclass(frozen=True)
class NFLV2HTeamState:
    games: int
    drives: int
    td_xp_good: int
    td_xp_miss: int
    td_two_good: int
    td_two_fail: int
    field_goals: int
    safeties: int
    drives_faced: int
    td_xp_good_allowed: int
    td_xp_miss_allowed: int
    td_two_good_allowed: int
    td_two_fail_allowed: int
    field_goals_allowed: int
    safeties_allowed: int


@dataclass(frozen=True)
class NFLM2V2HCandidateModel:
    model_id: str
    distribution_contract: str
    event_contract: str
    train_seasons: tuple[int, ...]
    league_drives_per_team_game: float
    league_event_rates: Mapping[str, float]
    team_state: Mapping[str, NFLV2HTeamState]
    prior_drives: float
    max_events_per_type: int


def _conversion_state(row: Mapping[str, Any], state: dict[str, Any]) -> None:
    xp = str(row.get("extra_point_result") or "").strip().lower()
    two = str(row.get("two_point_conv_result") or "").strip().lower()
    if xp:
        if xp in {"good", "made", "success", "successful"}:
            state["xp"] = "good"
        elif xp in {"failed", "missed", "no_good", "blocked"}:
            state["xp"] = "miss"
    if two:
        if two in {"success", "successful", "good"}:
            state["two"] = "good"
        elif two in {"failure", "failed", "fail", "no_good"}:
            state["two"] = "fail"


def build_nfl_v2h_game_event_rows(
    schedule_rows: Iterable[Mapping[str, Any]],
    pbp_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    schedule: dict[str, dict[str, Any]] = {}
    for raw in schedule_rows:
        row = dict(raw)
        game_id = str(row.get("game_id") or "").strip()
        if not game_id or str(row.get("game_type") or "REG").upper() != "REG":
            continue
        home = str(row.get("home_team") or "").strip()
        away = str(row.get("away_team") or "").strip()
        season = _int(row.get("season"))
        if not home or not away or home == away or season is None:
            raise ValueError(f"NFL_M2_V2H_SCHEDULE_IDENTITY_INVALID:{game_id}")
        schedule[game_id] = row

    drives: dict[tuple[str, str, str], dict[str, Any]] = {}
    safeties: dict[tuple[str, str], int] = {}
    games_seen: set[str] = set()
    for raw in pbp_rows:
        row = dict(raw)
        game_id = str(row.get("game_id") or "").strip()
        game = schedule.get(game_id)
        if game is None:
            continue
        home = str(game["home_team"])
        away = str(game["away_team"])
        posteam = str(row.get("posteam") or "").strip()
        drive = str(row.get("drive") or "").strip()
        if posteam not in {home, away}:
            continue
        if not drive:
            scoring_signal = _one(row.get("touchdown")) or _one(row.get("safety")) or str(row.get("field_goal_result") or "").strip()
            if scoring_signal:
                raise ValueError(f"NFL_M2_V2H_SCORING_IDENTITY_MISSING:{game_id}")
            continue
        key = (game_id, posteam, drive)
        state = drives.setdefault(key, {"touchdown": False, "field_goal": False, "xp": None, "two": None})
        if _one(row.get("touchdown")):
            td_team = str(row.get("td_team") or "").strip()
            if td_team == posteam:
                state["touchdown"] = True
        play_type = str(row.get("play_type") or "").strip().lower()
        fg_result = str(row.get("field_goal_result") or "").strip().lower()
        if play_type == "field_goal" and fg_result == "made":
            state["field_goal"] = True
        _conversion_state(row, state)
        if _one(row.get("safety")):
            scoring_team = away if posteam == home else home
            safeties[(game_id, scoring_team)] = safeties.get((game_id, scoring_team), 0) + 1
        games_seen.add(game_id)

    aggregates: dict[tuple[str, str], dict[str, int]] = {}
    for (game_id, team, _drive), state in drives.items():
        agg = aggregates.setdefault((game_id, team), {
            "drives": 0,
            "td_xp_good": 0,
            "td_xp_miss": 0,
            "td_two_good": 0,
            "td_two_fail": 0,
            "field_goals": 0,
            "other_no_score": 0,
        })
        agg["drives"] += 1
        if state["touchdown"]:
            if state["two"] == "good":
                agg["td_two_good"] += 1
            elif state["two"] == "fail":
                agg["td_two_fail"] += 1
            elif state["xp"] == "miss":
                agg["td_xp_miss"] += 1
            else:
                agg["td_xp_good"] += 1
        elif state["field_goal"]:
            agg["field_goals"] += 1
        else:
            agg["other_no_score"] += 1

    output: list[dict[str, Any]] = []
    for game_id in sorted(games_seen):
        game = schedule[game_id]
        home = str(game["home_team"])
        away = str(game["away_team"])
        home_events = aggregates.get((game_id, home))
        away_events = aggregates.get((game_id, away))
        if not home_events or not away_events:
            raise ValueError(f"NFL_M2_V2H_TEAM_POSSESSIONS_MISSING:{game_id}")
        row: dict[str, Any] = {
            "event_contract": NFL_M2_V2H_EVENT_CONTRACT,
            "game_id": game_id,
            "season": int(game["season"]),
            "week": game.get("week"),
            "home_team": home,
            "away_team": away,
        }
        for side, team, events in (("home", home, home_events), ("away", away, away_events)):
            for key, value in events.items():
                row[f"{side}_{key}"] = int(value)
            row[f"{side}_safeties"] = int(safeties.get((game_id, team), 0))
        for field in (
            "home_score", "away_score", "spread_line", "total_line",
            "home_spread_odds", "away_spread_odds", "over_odds", "under_odds",
        ):
            if field in game:
                row[field] = game[field]
        output.append(row)
    return output


def _validate_training_row(row: Mapping[str, Any]) -> tuple[str, str, int, dict[str, int]]:
    if str(row.get("event_contract") or "") != NFL_M2_V2H_EVENT_CONTRACT:
        raise ValueError("NFL_M2_V2H_EVENT_CONTRACT_INVALID")
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    season = _int(row.get("season"))
    if not home or not away or home == away or season is None:
        raise ValueError("NFL_M2_V2H_TRAINING_IDENTITY_INVALID")
    counts: dict[str, int] = {}
    event_keys = ("td_xp_good", "td_xp_miss", "td_two_good", "td_two_fail", "field_goals")
    for side in ("home", "away"):
        drives = _int(row.get(f"{side}_drives"))
        other = _int(row.get(f"{side}_other_no_score"))
        safety = _int(row.get(f"{side}_safeties"))
        if None in (drives, other, safety):
            raise ValueError("NFL_M2_V2H_EVENT_COUNT_MISSING")
        subtotal = int(other)
        counts[f"{side}_drives"] = int(drives)
        counts[f"{side}_other_no_score"] = int(other)
        counts[f"{side}_safeties"] = int(safety)
        for key in event_keys:
            value = _int(row.get(f"{side}_{key}"))
            if value is None or value < 0:
                raise ValueError("NFL_M2_V2H_EVENT_COUNT_MISSING")
            counts[f"{side}_{key}"] = value
            subtotal += value
        if int(drives) <= 0 or int(other) < 0 or int(safety) < 0 or subtotal != int(drives):
            raise ValueError("NFL_M2_V2H_EVENT_COUNT_INVALID")
    return home, away, season, counts


def fit_nfl_m2_v2h_candidate(
    rows: Iterable[Mapping[str, Any]],
    *,
    prior_drives: float = 48.0,
    max_events_per_type: int = 9,
) -> NFLM2V2HCandidateModel:
    data = [dict(row) for row in rows]
    if len(data) < 2:
        raise ValueError("NFL_M2_V2H_TRAINING_ROWS_INSUFFICIENT")
    if not isfinite(float(prior_drives)) or prior_drives <= 0 or max_events_per_type < 1:
        raise ValueError("NFL_M2_V2H_PARAMETER_INVALID")
    keys = tuple(_EVENT_POINTS)
    totals = {"games": 0, "drives": 0, **{key: 0 for key in keys}}
    mutable: dict[str, dict[str, int]] = {}
    seasons: set[int] = set()

    def blank() -> dict[str, int]:
        return {
            "games": 0,
            "drives": 0,
            "faced": 0,
            **{key: 0 for key in keys},
            **{f"{key}_allowed": 0 for key in keys},
        }

    for row in data:
        home, away, season, counts = _validate_training_row(row)
        seasons.add(season)
        totals["games"] += 2
        for side, team, opponent in (("home", home, away), ("away", away, home)):
            drives = counts[f"{side}_drives"]
            totals["drives"] += drives
            own = mutable.setdefault(team, blank())
            opp = mutable.setdefault(opponent, blank())
            own["games"] += 1
            own["drives"] += drives
            opp["faced"] += drives
            for key in keys:
                if key == "field_goal":
                    source = "field_goals"
                elif key == "safety":
                    source = "safeties"
                else:
                    source = key
                value = counts[f"{side}_{source}"]
                own[key] += value
                opp[f"{key}_allowed"] += value
                totals[key] += value

    if totals["drives"] <= 0:
        raise ValueError("NFL_M2_V2H_LEAGUE_STATE_EMPTY")
    league_rates = {key: totals[key] / float(totals["drives"]) for key in keys}
    states: dict[str, NFLV2HTeamState] = {}
    for team, value in sorted(mutable.items()):
        states[team] = NFLV2HTeamState(
            games=value["games"],
            drives=value["drives"],
            td_xp_good=value["td_xp_good"],
            td_xp_miss=value["td_xp_miss"],
            td_two_good=value["td_two_good"],
            td_two_fail=value["td_two_fail"],
            field_goals=value["field_goal"],
            safeties=value["safety"],
            drives_faced=value["faced"],
            td_xp_good_allowed=value["td_xp_good_allowed"],
            td_xp_miss_allowed=value["td_xp_miss_allowed"],
            td_two_good_allowed=value["td_two_good_allowed"],
            td_two_fail_allowed=value["td_two_fail_allowed"],
            field_goals_allowed=value["field_goal_allowed"],
            safeties_allowed=value["safety_allowed"],
        )
    return NFLM2V2HCandidateModel(
        model_id=NFL_M2_V2H_CANDIDATE_MODEL_ID,
        distribution_contract=NFL_M2_V2H_DISTRIBUTION_CONTRACT,
        event_contract=NFL_M2_V2H_EVENT_CONTRACT,
        train_seasons=tuple(sorted(seasons)),
        league_drives_per_team_game=totals["drives"] / float(totals["games"]),
        league_event_rates=league_rates,
        team_state=states,
        prior_drives=float(prior_drives),
        max_events_per_type=int(max_events_per_type),
    )


def _rate(events: int, drives: int, league: float, prior: float) -> float:
    return (events + prior * league) / (drives + prior)


def _poisson(lam: float, maximum: int) -> list[float]:
    values = [exp(-lam) * lam ** k / factorial(k) for k in range(maximum + 1)]
    total = sum(values)
    if total <= 0 or not isfinite(total):
        raise ValueError("NFL_M2_V2H_POISSON_NORMALIZATION_FAILED")
    return [value / total for value in values]


def _event_projection(
    model: NFLM2V2HCandidateModel,
    offense: str,
    defense: str,
) -> tuple[float, dict[str, float]]:
    off = model.team_state.get(offense)
    deff = model.team_state.get(defense)
    if off is None or deff is None:
        raise ValueError(f"NFL_M2_V2H_TEAM_STATE_MISSING:{offense}:{defense}")
    off_drives = off.drives / float(off.games) if off.games else model.league_drives_per_team_game
    def_drives = deff.drives_faced / float(deff.games) if deff.games else model.league_drives_per_team_game
    drives = max(1.0, (off_drives + def_drives + model.league_drives_per_team_game) / 3.0)
    rates: dict[str, float] = {}
    attr = {"field_goal": "field_goals", "safety": "safeties"}
    for key, league in model.league_event_rates.items():
        own_name = attr.get(key, key)
        allow_name = f"{own_name}_allowed"
        own = _rate(getattr(off, own_name), off.drives, league, model.prior_drives)
        allowed = _rate(getattr(deff, allow_name), deff.drives_faced, league, model.prior_drives)
        rates[key] = _clamp(sqrt(own * allowed), 0.80 if key.startswith("td_") else 0.50)
    return drives, rates


def _team_score_distribution(
    model: NFLM2V2HCandidateModel,
    offense: str,
    defense: str,
) -> dict[int, float]:
    drives, rates = _event_projection(model, offense, defense)
    score_pmf = {0: 1.0}
    for key, points in _EVENT_POINTS.items():
        pmf = _poisson(drives * rates[key], model.max_events_per_type)
        next_pmf: dict[int, float] = {}
        for prior_score, prior_prob in score_pmf.items():
            for count, probability in enumerate(pmf):
                score = prior_score + points * count
                next_pmf[score] = next_pmf.get(score, 0.0) + prior_prob * probability
        score_pmf = next_pmf
    total = sum(score_pmf.values())
    return {score: probability / total for score, probability in sorted(score_pmf.items())}


def derive_nfl_m2_v2h_score_distribution(
    model: NFLM2V2HCandidateModel,
    row: Mapping[str, Any],
) -> tuple[dict[str, float | int], ...]:
    if model.model_id != NFL_M2_V2H_CANDIDATE_MODEL_ID or model.distribution_contract != NFL_M2_V2H_DISTRIBUTION_CONTRACT:
        raise ValueError("NFL_M2_V2H_MODEL_IDENTITY_INVALID")
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    if not home or not away or home == away:
        raise ValueError("NFL_M2_V2H_PREDICTION_IDENTITY_INVALID")
    _ = tuple(field for field in _MARKET_FIELDS if field in row)
    home_scores = _team_score_distribution(model, home, away)
    away_scores = _team_score_distribution(model, away, home)
    distribution = tuple(
        {
            "home_score": int(home_score),
            "away_score": int(away_score),
            "margin": int(home_score - away_score),
            "total": int(home_score + away_score),
            "weight": float(home_prob * away_prob),
        }
        for home_score, home_prob in home_scores.items()
        for away_score, away_prob in away_scores.items()
    )
    if abs(sum(float(item["weight"]) for item in distribution) - 1.0) > 1e-10:
        raise ValueError("NFL_M2_V2H_WEIGHT_CONSERVATION_FAILED")
    return distribution
