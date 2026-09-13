"""Research-only CFB Stage 1 prop-volume engine.

Market-blind count distributions for pass attempts, rush attempts, targets and
receptions. No Model_P/OFFICIAL/promotion/staking or market-binding authority.
"""
from __future__ import annotations

from sportsedge.sports.nfl.prop_volume_stage1 import (
    NFLVolumeStage1,
    VolumeDistribution,
    VolumeStage1Error,
    _assert_market_blind,
)

MODEL_ID = "CFB_PROP_VOLUME_STAGE1_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"
SUPPORTED_COUNTS = ("pass_attempts", "rush_attempts", "targets", "receptions")


class CFBVolumeStage1(NFLVolumeStage1):
    """CFB opportunity model using the same market-blind count mechanics.

    CFB-specific context (tempo, depth chart, participation, QB status and role
    share) must be resolved upstream with PIT timestamps before calling project.
    """

    def __init__(self, *, decay: float = 0.78, shrink_games: float = 3.0):
        super().__init__(decay=decay, shrink_games=shrink_games)

    def project(self, **kwargs) -> VolumeDistribution:  # type: ignore[override]
        _assert_market_blind(kwargs)
        out = super().project(**kwargs)
        return VolumeDistribution(
            player_id=out.player_id,
            metric=out.metric,
            mean=out.mean,
            pmf=out.pmf,
            max_explicit_count=out.max_explicit_count,
            model_id=MODEL_ID,
            status=STATUS,
        )


__all__ = ["CFBVolumeStage1", "VolumeDistribution", "VolumeStage1Error"]
