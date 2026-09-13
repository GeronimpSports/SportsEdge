"""Research-only NFL Stage 1 prop-volume engine.

Produces market-blind count distributions for pass attempts, rush attempts,
targets and receptions. This module grants no Model_P/OFFICIAL/promotion/staking
or sportsbook-binding authority. Downstream prop pricing remains blocked until
all later stages and validation pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, lgamma, log
from typing import Iterable, Mapping

MODEL_ID = "NFL_PROP_VOLUME_STAGE1_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"
SUPPORTED_COUNTS = ("pass_attempts", "rush_attempts", "targets", "receptions")
BANNED_KEYS = {
    "odds", "price", "line", "spread", "total", "sportsbook", "book",
    "american_odds", "decimal_odds", "implied_probability", "no_vig_probability",
    "closing_line", "opening_line", "prop_line", "over_price", "under_price",
}


class VolumeStage1Error(ValueError):
    pass


def _assert_market_blind(obj: object) -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            key = str(k).lower()
            if key in BANNED_KEYS or any(tok in key for tok in ("sportsbook", "closing_odds", "market_price")):
                raise VolumeStage1Error(f"MARKET_DERIVED_INPUT_FORBIDDEN:{k}")
            _assert_market_blind(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _assert_market_blind(v)


def _poisson_pmf(mean: float, max_count: int) -> tuple[float, ...]:
    if not (mean > 0.0):
        raise VolumeStage1Error("MEAN_MUST_BE_POSITIVE")
    if max_count < 1:
        raise VolumeStage1Error("MAX_COUNT_TOO_SMALL")
    vals = [exp(-mean + k * log(mean) - lgamma(k + 1.0)) for k in range(max_count)]
    tail = max(0.0, 1.0 - sum(vals))
    vals.append(tail)
    total = sum(vals)
    return tuple(v / total for v in vals)


def _weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    pairs = [(float(v), float(w)) for v, w in zip(values, weights) if float(w) > 0]
    if not pairs:
        raise VolumeStage1Error("NO_POSITIVE_WEIGHT_HISTORY")
    sw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / sw


@dataclass(frozen=True)
class VolumeDistribution:
    player_id: str
    metric: str
    mean: float
    pmf: tuple[float, ...]
    max_explicit_count: int
    model_id: str = MODEL_ID
    status: str = STATUS

    def probability_over(self, line: float) -> float:
        threshold = int(line // 1 + 1)
        return sum(self.pmf[threshold:]) if threshold < len(self.pmf) else 0.0

    def probability_under(self, line: float) -> float:
        return 1.0 - self.probability_over(line)


class NFLVolumeStage1:
    """Recency-weighted opportunity model with role and team-volume conditioning.

    Inputs must be PIT-safe, pre-kickoff football information only. The model
    intentionally has no sportsbook-line argument.
    """

    def __init__(self, *, decay: float = 0.82, shrink_games: float = 4.0):
        if not 0.0 < decay <= 1.0:
            raise VolumeStage1Error("BAD_DECAY")
        if shrink_games < 0:
            raise VolumeStage1Error("BAD_SHRINK_GAMES")
        self.decay = float(decay)
        self.shrink_games = float(shrink_games)

    def project(
        self,
        *,
        player_id: str,
        metric: str,
        history: list[Mapping[str, object]],
        team_opportunity_mean: float,
        role_share: float,
        availability_probability: float = 1.0,
        max_count: int | None = None,
    ) -> VolumeDistribution:
        payload = {
            "history": history,
            "team_opportunity_mean": team_opportunity_mean,
            "role_share": role_share,
            "availability_probability": availability_probability,
        }
        _assert_market_blind(payload)
        if metric not in SUPPORTED_COUNTS:
            raise VolumeStage1Error(f"UNSUPPORTED_METRIC:{metric}")
        if not player_id:
            raise VolumeStage1Error("PLAYER_ID_REQUIRED")
        if not 0 <= role_share <= 1:
            raise VolumeStage1Error("ROLE_SHARE_OUT_OF_RANGE")
        if not 0 <= availability_probability <= 1:
            raise VolumeStage1Error("AVAILABILITY_OUT_OF_RANGE")
        if team_opportunity_mean <= 0:
            raise VolumeStage1Error("TEAM_OPPORTUNITY_MEAN_MUST_BE_POSITIVE")

        observed: list[float] = []
        for row in history:
            if metric in row:
                val = float(row[metric])
                if val < 0:
                    raise VolumeStage1Error("NEGATIVE_HISTORY_COUNT")
                observed.append(val)
        if not observed:
            raise VolumeStage1Error("NO_METRIC_HISTORY")

        # newest row gets weight 1; older rows decay geometrically.
        n = len(observed)
        weights = [self.decay ** (n - 1 - i) for i in range(n)]
        hist_mean = _weighted_mean(observed, weights)
        role_based = float(team_opportunity_mean) * float(role_share)
        hist_weight = sum(weights)
        denom = hist_weight + self.shrink_games
        mean = ((hist_mean * hist_weight) + (role_based * self.shrink_games)) / max(denom, 1e-12)
        mean *= float(availability_probability)
        mean = max(mean, 1e-6)

        default_caps = {"pass_attempts": 70, "rush_attempts": 45, "targets": 30, "receptions": 25}
        cap = int(max_count if max_count is not None else default_caps[metric])
        return VolumeDistribution(
            player_id=player_id,
            metric=metric,
            mean=mean,
            pmf=_poisson_pmf(mean, cap),
            max_explicit_count=cap,
        )
