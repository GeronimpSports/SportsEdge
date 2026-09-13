"""Fail-closed PIT input/provenance contract for research prop engines."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Mapping
from sportsedge.props_joint_stage3 import reject_market_inputs

REQUIRED_COMMON=("asof_ts","event_start_ts","source_id","entity_id","availability_status")
REQUIRED={
 "NFL":("snap_share","role_share","depth_status","qb_status","weather_status","opponent_feature_asof_ts"),
 "CFB":("snap_share","role_share","depth_status","qb_status","weather_status","opponent_feature_asof_ts"),
 "MLB":("lineup_status","batting_order_or_pitcher_role","starter_status","bullpen_status","park_roof_status","weather_status","opponent_feature_asof_ts"),
}
def _dt(v:str)->datetime:return datetime.fromisoformat(str(v).replace("Z","+00:00"))
def validate_pit_inputs(sport:str,payload:Mapping[str,Any])->dict[str,Any]:
    reject_market_inputs(payload)
    if sport not in REQUIRED:raise ValueError("UNSUPPORTED_SPORT")
    missing=[k for k in REQUIRED_COMMON+REQUIRED[sport] if k not in payload]
    if missing:raise ValueError("PIT_FIELDS_MISSING:"+",".join(missing))
    if _dt(payload["asof_ts"])>_dt(payload["event_start_ts"]):raise ValueError("PIT_AFTER_EVENT_START")
    if _dt(payload["opponent_feature_asof_ts"])>_dt(payload["event_start_ts"]):raise ValueError("OPPONENT_FEATURE_AFTER_EVENT_START")
    out=dict(payload);out["pit_validated"]=True;out["sport"]=sport;return out
