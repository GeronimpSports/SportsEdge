"""Research-only CFB prop efficiency layer. No sportsbook binding or production authority."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite
from typing import Any, Mapping

BANNED_KEYS = {"odds","price","line","spread","total","sportsbook","book","market","closing_line","implied_probability"}
SUPPORTED_METRICS = {"completion_rate","yards_per_attempt","yards_per_carry","catch_rate","yards_per_target","yac_per_reception"}
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"


def _reject_market_inputs(value: Any) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():
            if str(k).lower() in BANNED_KEYS:
                raise ValueError(f"MARKET_INPUT_FORBIDDEN:{k}")
            _reject_market_inputs(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_market_inputs(v)


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


@dataclass(frozen=True)
class EfficiencyDistribution:
    sport: str
    metric: str
    mean: float
    sd: float
    status: str = STATUS

    def probability_over(self, threshold: float) -> float:
        z = (self.mean - float(threshold)) / max(self.sd, 1e-9)
        return _logistic(1.702 * z)


def build_efficiency_distribution(metric: str, pit_inputs: Mapping[str, Any]) -> EfficiencyDistribution:
    _reject_market_inputs(pit_inputs)
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"UNSUPPORTED_STAGE2_METRIC:{metric}")
    baseline = float(pit_inputs["baseline"])
    context_delta = float(pit_inputs.get("context_delta", 0.0))
    uncertainty = float(pit_inputs.get("uncertainty", 0.10 if "rate" in metric else 1.25))
    if not all(isfinite(x) for x in (baseline, context_delta, uncertainty)) or uncertainty <= 0:
        raise ValueError("INVALID_EFFICIENCY_INPUT")
    mean = baseline + context_delta
    if metric in {"completion_rate", "catch_rate"}:
        mean = min(0.999, max(0.001, mean))
    return EfficiencyDistribution("CFB", metric, mean, uncertainty)
