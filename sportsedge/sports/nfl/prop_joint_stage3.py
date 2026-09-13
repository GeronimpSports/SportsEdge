"""Research-only NFL Stage 3 joint player distributions.

Couples Stage 1 opportunity volume with Stage 2 efficiency into coherent player
paths. No sportsbook binding, Model_P, promotion, OFFICIAL, or staking authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Mapping, Any

from sportsedge.sports.nfl.prop_volume_stage1 import VolumeDistribution, _assert_market_blind
from sportsedge.sports.nfl.prop_efficiency_engine import EfficiencyDistribution

MODEL_ID = "NFL_PROP_JOINT_STAGE3_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"


@dataclass(frozen=True)
class JointPlayerDistribution:
    player_id: str
    samples: tuple[Mapping[str, int], ...]
    model_id: str = MODEL_ID
    status: str = STATUS

    def probability_over(self, metric: str, line: float) -> float:
        if not self.samples:
            raise ValueError("NO_SAMPLES")
        return sum(float(row[metric]) > line for row in self.samples) / len(self.samples)


def _draw_discrete(rng: Random, pmf: tuple[float, ...]) -> int:
    u = rng.random()
    c = 0.0
    for i, p in enumerate(pmf):
        c += p
        if u <= c:
            return i
    return len(pmf) - 1


def build_joint_player_distribution(
    *,
    player_id: str,
    volume: Mapping[str, VolumeDistribution],
    efficiency: Mapping[str, EfficiencyDistribution],
    seed: int,
    paths: int = 50000,
    pit_context: Mapping[str, Any] | None = None,
) -> JointPlayerDistribution:
    _assert_market_blind(pit_context or {})
    if paths < 1000:
        raise ValueError("TOO_FEW_PATHS")
    rng = Random(int(seed))
    rows: list[Mapping[str, int]] = []
    for _ in range(paths):
        if "pass_attempts" in volume:
            att = _draw_discrete(rng, volume["pass_attempts"].pmf)
            cr = efficiency["completion_rate"].mean
            comp = sum(rng.random() < cr for _ in range(att))
            ypa = max(0.0, rng.gauss(efficiency["yards_per_attempt"].mean, efficiency["yards_per_attempt"].sd))
            pass_yards = int(round(att * ypa))
            rows.append({"pass_attempts": att, "completions": comp, "passing_yards": pass_yards})
        elif "targets" in volume:
            targets = _draw_discrete(rng, volume["targets"].pmf)
            catch = efficiency["catch_rate"].mean
            receptions = sum(rng.random() < catch for _ in range(targets))
            ypt = max(0.0, rng.gauss(efficiency["yards_per_target"].mean, efficiency["yards_per_target"].sd))
            rec_yards = int(round(targets * ypt))
            rows.append({"targets": targets, "receptions": receptions, "receiving_yards": rec_yards})
        elif "rush_attempts" in volume:
            carries = _draw_discrete(rng, volume["rush_attempts"].pmf)
            ypc = max(0.0, rng.gauss(efficiency["yards_per_carry"].mean, efficiency["yards_per_carry"].sd))
            rush_yards = int(round(carries * ypc))
            rows.append({"rush_attempts": carries, "rushing_yards": rush_yards})
        else:
            raise ValueError("UNSUPPORTED_STAGE3_VOLUME_SHAPE")
    return JointPlayerDistribution(player_id=player_id, samples=tuple(rows))
