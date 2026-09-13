"""Fail-closed PIT input/provenance contract for research prop engines."""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping
from sportsedge.props_joint_stage3 import reject_market_inputs

REQUIRED_COMMON=("asof_ts","event_start_ts","source_id","entity_id","availability_status")
REQUIRED={
 "NFL":("snap_share","role_share","depth_status","qb_status","weather_status","opponent_feature_asof_ts"),
 "CFB":("snap_share","role_share","depth_status","qb_status","weather_status","opponent_feature_asof_ts"),
 "MLB":("lineup_status","batting_order_or_pitcher_role","starter_status","bullpen_status","park_roof_status","weather_status","opponent_feature_asof_ts"),
}

def _dt(v:str,name:str)->datetime:
    try:
        value=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except (TypeError,ValueError) as exc:
        raise ValueError(f"PIT_TIMESTAMP_INVALID:{name}") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PIT_TIMESTAMP_MUST_BE_TIMEZONE_AWARE:{name}")
    return value

def _canonical_sha256(value:Any)->str:
    try:
        raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise ValueError("PIT_CANONICALIZATION_INVALID") from exc
    return sha256(raw).hexdigest()

def pit_record_sha256(sport:str,payload:Mapping[str,Any])->str:
    """Hash the exact pre-model PIT record without derived validation markers."""
    clean=dict(payload)
    clean.pop("pit_validated",None)
    clean.pop("pit_record_sha256",None)
    clean.pop("sport",None)
    return _canonical_sha256({"schema":"PROP_PIT_RECORD_V1","sport":str(sport),"payload":clean})

def validate_pit_inputs(sport:str,payload:Mapping[str,Any])->dict[str,Any]:
    reject_market_inputs(payload)
    if sport not in REQUIRED:raise ValueError("UNSUPPORTED_SPORT")
    missing=[k for k in REQUIRED_COMMON+REQUIRED[sport] if k not in payload]
    if missing:raise ValueError("PIT_FIELDS_MISSING:"+",".join(missing))
    asof=_dt(payload["asof_ts"],"asof_ts")
    event_start=_dt(payload["event_start_ts"],"event_start_ts")
    opponent_asof=_dt(payload["opponent_feature_asof_ts"],"opponent_feature_asof_ts")
    if asof>=event_start:raise ValueError("PIT_NOT_STRICTLY_BEFORE_EVENT_START")
    if opponent_asof>asof:raise ValueError("OPPONENT_FEATURE_AFTER_DECISION_ASOF")
    out=dict(payload)
    out["pit_validated"]=True
    out["sport"]=sport
    out["pit_record_sha256"]=pit_record_sha256(sport,payload)
    return out
