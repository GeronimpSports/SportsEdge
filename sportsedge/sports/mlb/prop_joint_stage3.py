"""Research-only MLB Stage 3 joint hitter/pitcher distributions."""
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Mapping, Any

from sportsedge.sports.mlb.prop_volume_stage1 import MLBOpportunityDistribution, _assert_market_blind
from sportsedge.sports.mlb.prop_efficiency_engine import EfficiencyDistribution

MODEL_ID = "MLB_PROP_JOINT_STAGE3_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"


@dataclass(frozen=True)
class MLBJointPlayerDistribution:
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


def build_hitter_distribution(
    *,
    player_id: str,
    plate_appearances: MLBOpportunityDistribution,
    efficiency: Mapping[str, EfficiencyDistribution],
    seed: int,
    paths: int = 50000,
    pit_context: Mapping[str, Any] | None = None,
) -> MLBJointPlayerDistribution:
    _assert_market_blind(pit_context or {})
    if paths < 1000:
        raise ValueError("TOO_FEW_PATHS")
    rng = Random(int(seed))
    rows: list[Mapping[str, int]] = []
    for _ in range(paths):
        pa = _draw_discrete(rng, plate_appearances.pmf)
        k = bb = hits = xbh = 0
        for _ in range(pa):
            u = rng.random()
            k_rate = efficiency["strikeout_rate"].mean
            bb_rate = efficiency["walk_rate"].mean
            if u < k_rate:
                k += 1
                continue
            if u < k_rate + bb_rate:
                bb += 1
                continue
            if rng.random() < efficiency["hit_rate"].mean:
                hits += 1
                if rng.random() < efficiency["extra_base_hit_rate"].mean:
                    xbh += 1
        total_bases = hits + xbh
        rows.append({"plate_appearances": pa, "strikeouts": k, "walks": bb, "hits": hits, "extra_base_hits": xbh, "total_bases": total_bases})
    return MLBJointPlayerDistribution(player_id=player_id, samples=tuple(rows))


def build_pitcher_distribution(
    *,
    player_id: str,
    batters_faced: MLBOpportunityDistribution,
    efficiency: Mapping[str, EfficiencyDistribution],
    seed: int,
    paths: int = 50000,
    pit_context: Mapping[str, Any] | None = None,
) -> MLBJointPlayerDistribution:
    _assert_market_blind(pit_context or {})
    if paths < 1000:
        raise ValueError("TOO_FEW_PATHS")
    rng = Random(int(seed))
    rows: list[Mapping[str, int]] = []
    for _ in range(paths):
        bf = _draw_discrete(rng, batters_faced.pmf)
        k = bb = hits = outs = 0
        for _ in range(bf):
            u = rng.random()
            if u < efficiency["strikeout_rate"].mean:
                k += 1; outs += 1; continue
            if u < efficiency["strikeout_rate"].mean + efficiency["walk_rate"].mean:
                bb += 1; continue
            if rng.random() < efficiency["hit_rate"].mean:
                hits += 1
            else:
                outs += 1
        rows.append({"batters_faced": bf, "strikeouts": k, "walks_allowed": bb, "hits_allowed": hits, "outs": outs})
    return MLBJointPlayerDistribution(player_id=player_id, samples=tuple(rows))
