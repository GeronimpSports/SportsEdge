"""Immutable V2L model-input source manifest. Research-only."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json
from typing import Iterable, Mapping

SCHEMA="SPORTSEDGE_NFL_V2L_SOURCE_MANIFEST_V1"

def _sha(v,label):
    s=str(v or "")
    if len(s)!=64 or any(c not in "0123456789abcdefABCDEF" for c in s): raise ValueError(f"{label} must be SHA256")
    return s.lower()

def _utc(v):
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None: raise ValueError("timezone-aware retrieval timestamp required")
    return d.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def build_source_manifest(files: Iterable[Mapping[str,object]], *, dataset_version: str, provider: str="nflverse/nflfastR") -> dict:
    rows=[]
    for f in files:
        for k in ("name","source_identifier","season_scope","week_scope","retrieved_at_utc","byte_sha256","parser_code_sha256"):
            if f.get(k) in (None,"",[]): raise ValueError(f"{k} required")
        rows.append({"name":str(f["name"]),"source_identifier":str(f["source_identifier"]),"season_scope":f["season_scope"],"week_scope":f["week_scope"],"retrieved_at_utc":_utc(f["retrieved_at_utc"]),"byte_sha256":_sha(f["byte_sha256"],"byte_sha256"),"parser_code_sha256":_sha(f["parser_code_sha256"],"parser_code_sha256")})
    if not rows or not str(dataset_version).strip(): raise ValueError("files and pinned dataset version required")
    rows.sort(key=lambda x:(x["name"],x["source_identifier"]))
    out={"schema":SCHEMA,"provider":provider,"dataset_version":str(dataset_version),"required_training_identity_fields":["posteam","defteam"],"files":rows,"model_p_authority":False,"promotion_authority":False,"official_authority":False}
    out["manifest_sha256"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":")).encode()).hexdigest(); return out
