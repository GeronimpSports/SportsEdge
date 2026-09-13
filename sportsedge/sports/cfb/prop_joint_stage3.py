"""Research-only CFB Stage 3 joint player distributions."""
from __future__ import annotations

from sportsedge.sports.nfl.prop_joint_stage3 import (
    JointPlayerDistribution,
    build_joint_player_distribution as _build_nfl_joint,
)

MODEL_ID = "CFB_PROP_JOINT_STAGE3_V1"
STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"


def build_joint_player_distribution(**kwargs) -> JointPlayerDistribution:
    out = _build_nfl_joint(**kwargs)
    return JointPlayerDistribution(
        player_id=out.player_id,
        samples=out.samples,
        model_id=MODEL_ID,
        status=STATUS,
    )
