"""Research-only MLB Stage 1 opportunity-volume engine.

Produces market-blind count distributions for batter plate appearances and
pitcher batters faced / pitches thrown. No Model_P/OFFICIAL/promotion/staking
or sportsbook-binding authority is granted.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, lgamma, log
from typing import Mapping

MODEL_ID = "MLB_PROP_VOLUME_STAGE1_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"
SUPPORTED_COUNTS = ("plate_appearances", "batters_faced", "pitches_thrown")
BANNED_KEYS = {
    "odds", "price", "line", "sportsbook", "book", "american_odds",
    "decimal_odds", "implied_probability", "no_vig_probability", "prop_line",
    "over_price", "under_price", "closing_line", "opening_line",
}


class MLBVolumeStage1Error(ValueError):
    pass


def _assert_market_blind(obj: object) -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            key = str(k).lower()
            if key in BANNED_KEYS or any(tok in key for tok in ("sportsbook", "closing_odds", "market_price")):
                raise MLBVolumeStage1Error(f"MARKET_DERIVED_INPUT_FORBIDDEN:{k}")
            _assert_market_blind(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _assert_market_blind(v)


def _poisson_pmf(mean: float, max_count: int) -> tuple[float, ...]:
    if mean <= 0:
        raise MLBVolumeStage1Error("MEAN_MUST_BE_POSITIVE")
    vals = [exp(-mean + k * log(mean) - lgamma(k + 1.0)) for k in range(max_count)]
    vals.append(max(0.0, 1.0 - sum(vals)))
    total = sum(vals)
    return tuple(v / total for v in vals)


@dataclass(frozen=True)
class MLBOpportunityDistribution:
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


class MLBVolumeStage1:
    """PIT-safe opportunity model for hitters and pitchers.

    Inputs represent opportunity only: batting-order slot, team PA environment,
    starter leash / expected batters faced and historical usage. Contact quality,
    hit rate, strikeout rate and HR skill belong to later stages.
    """

    def __init__(self, *, decay: float = 0.86, shrink_games: float = 5.0):
        if not 0 < decay <= 1:
            raise MLBVolumeStage1Error("BAD_DECAY")
        if shrink_games < 0:
            raise MLBVolumeStage1Error("BAD_SHRINK_GAMES")
        self.decay = float(decay)
        self.shrink_games = float(shrink_games)

    def project(
        self,
        *,
        player_id: str,
        metric: str,
        history: list[Mapping[str, object]],
        role_opportunity_mean: float,
        availability_probability: float = 1.0,
        max_count: int | None = None,
    ) -> MLBOpportunityDistribution:
        _assert_market_blind({
            "history": history,
            "role_opportunity_mean": role_opportunity_mean,
            "availability_probability": availability_probability,
        })
        if metric not in SUPPORTED_COUNTS:
            raise MLBVolumeStage1Error(f"UNSUPPORTED_METRIC:{metric}")
        if not player_id:
            raise MLBVolumeStage1Error("PLAYER_ID_REQUIRED")
        if role_opportunity_mean <= 0:
            raise MLBVolumeStage1Error("ROLE_OPPORTUNITY_MEAN_MUST_BE_POSITIVE")
        if not 0 <= availability_probability <= 1:
            raise MLBVolumeStage1Error("AVAILABILITY_OUT_OF_RANGE")

        observed = []
        for row in history:
            if metric in row:
                v = float(row[metric])
                if v < 0:
                    raise MLBVolumeStage1Error("NEGATIVE_HISTORY_COUNT")
                observed.append(v)
        if not observed:
            raise MLBVolumeStage1Error("NO_METRIC_HISTORY")

        n = len(observed)
        weights = [self.decay ** (n - 1 - i) for i in range(n)]
        sw = sum(weights)
        hist_mean = sum(v * w for v, w in zip(observed, weights)) / sw
        denom = sw + self.shrink_games
        mean = ((hist_mean * sw) + (float(role_opportunity_mean) * self.shrink_games)) / max(denom, 1e-12)
        mean *= float(availability_probability)
        mean = max(mean, 1e-6)

        default_caps = {"plate_appearances": 8, "batters_faced": 40, "pitches_thrown": 140}
        cap = int(max_count if max_count is not None else default_caps[metric])
        return MLBOpportunityDistribution(
            player_id=player_id,
            metric=metric,
            mean=mean,
            pmf=_poisson_pmf(mean, cap),
            max_explicit_count=cap,
        )
