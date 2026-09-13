"""Research-only NFL player outcome engine G1.

This module is intentionally market-blind. It builds prior-game-only features and
simple baseline distributions for independent validation. It has no runtime,
pricing, staking, or promotion authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, lgamma, log
from statistics import mean
from typing import Any, Iterable


@dataclass(frozen=True)
class OutcomeDistribution:
    family: str
    mean: float
    variance: float
    params: dict[str, float]

    def cdf_count(self, k: int) -> float:
        if k < 0:
            return 0.0
        if self.family == "poisson":
            lam = self.params["lambda"]
            p = exp(-lam)
            total = p
            for x in range(1, k + 1):
                p *= lam / x
                total += p
            return min(1.0, max(0.0, total))
        if self.family == "negative_binomial":
            r = self.params["r"]
            p_success = self.params["p"]
            total = 0.0
            for x in range(k + 1):
                log_pmf = (
                    lgamma(x + r)
                    - lgamma(r)
                    - lgamma(x + 1)
                    + r * log(p_success)
                    + x * log(1.0 - p_success)
                )
                total += exp(log_pmf)
            return min(1.0, max(0.0, total))
        raise ValueError(f"count CDF unsupported for {self.family}")

    def prob_over_count_line(self, line: float) -> float:
        # Sportsbook-style .5 lines map naturally to integer exceedance.
        threshold = int(line // 1)
        return 1.0 - self.cdf_count(threshold)


def fit_count_distribution(values: Iterable[float]) -> OutcomeDistribution:
    xs = [max(0.0, float(v)) for v in values]
    if not xs:
        raise ValueError("NFL_PROP_G1_EMPTY_COUNT_HISTORY")
    mu = mean(xs)
    if len(xs) == 1:
        var = mu
    else:
        var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    if var > mu + 1e-9 and mu > 0.0:
        r = (mu * mu) / (var - mu)
        p = r / (r + mu)
        return OutcomeDistribution("negative_binomial", mu, var, {"r": r, "p": p})
    return OutcomeDistribution("poisson", mu, max(mu, var), {"lambda": mu})


def _prior_rows(rows: list[dict[str, Any]], idx: int, player_id: str) -> list[dict[str, Any]]:
    current = rows[idx]
    season = int(current["season"])
    week = int(current["week"])
    out: list[dict[str, Any]] = []
    for j in range(idx):
        row = rows[j]
        if str(row.get("player_id") or "") != player_id:
            continue
        rseason = int(row["season"])
        rweek = int(row["week"])
        if (rseason, rweek) >= (season, week):
            raise ValueError("NFL_PROP_G1_NON_PIT_PRIOR_ROW")
        out.append(row)
    return out


def build_player_feature_rows(rows: Iterable[dict[str, Any]], *, min_prior_games: int = 3) -> list[dict[str, Any]]:
    """Build shifted player-game features from rows sorted by season/week/player.

    Required identity: player_id, season, week. Current-game outcome columns are
    copied only as labels; every feature is computed exclusively from earlier rows.
    """
    data = [dict(r) for r in rows]
    data.sort(key=lambda r: (int(r["season"]), int(r["week"]), str(r.get("player_id") or "")))
    output: list[dict[str, Any]] = []
    for idx, row in enumerate(data):
        player_id = str(row.get("player_id") or "").strip()
        if not player_id:
            raise ValueError("NFL_PROP_G1_PLAYER_ID_REQUIRED")
        prior = _prior_rows(data, idx, player_id)
        if len(prior) < min_prior_games:
            continue
        window = prior[-5:]

        def avg(key: str) -> float:
            vals = [float(r.get(key) or 0.0) for r in window]
            return mean(vals) if vals else 0.0

        targets = avg("targets")
        receptions = avg("receptions")
        rec_yards = avg("receiving_yards")
        carries = avg("carries")
        rush_yards = avg("rushing_yards")
        pass_attempts = avg("attempts")
        pass_yards = avg("passing_yards")
        output.append({
            "player_id": player_id,
            "season": int(row["season"]),
            "week": int(row["week"]),
            "position": row.get("position"),
            "team": row.get("team"),
            "opponent_team": row.get("opponent_team"),
            "prior_game_count": len(prior),
            "targets_l5": targets,
            "receptions_l5": receptions,
            "catch_rate_l5": (receptions / targets) if targets > 0 else 0.0,
            "receiving_yards_l5": rec_yards,
            "yards_per_target_l5": (rec_yards / targets) if targets > 0 else 0.0,
            "carries_l5": carries,
            "rushing_yards_l5": rush_yards,
            "yards_per_carry_l5": (rush_yards / carries) if carries > 0 else 0.0,
            "attempts_l5": pass_attempts,
            "passing_yards_l5": pass_yards,
            "yards_per_attempt_l5": (pass_yards / pass_attempts) if pass_attempts > 0 else 0.0,
            "label_receptions": row.get("receptions"),
            "label_receiving_yards": row.get("receiving_yards"),
            "label_rushing_yards": row.get("rushing_yards"),
            "label_passing_yards": row.get("passing_yards"),
        })
    return output


def receptions_distribution(prior_game_rows: Iterable[dict[str, Any]]) -> OutcomeDistribution:
    return fit_count_distribution(float(r.get("receptions") or 0.0) for r in prior_game_rows)
