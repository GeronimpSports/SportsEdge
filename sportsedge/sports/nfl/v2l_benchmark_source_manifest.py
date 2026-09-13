"""Immutable market-benchmark source manifest for V2L evaluation only."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json
from typing import Iterable, Mapping

SCHEMA="SPORTSEDGE_NFL_V2L_BENCHMARK_SOURCE_MANIFEST_V1"

def _sha(v,label):
    s=str(v or "")
    if len(s)!=64 or any(c not in "0123456789abcdefABCDEF" for c in s): raise ValueError(f"{label} must be SHA256")
    return s.lower()

def _utc(v):
    d=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None: raise ValueError("timezone-aware capture timestamp required")
    return d.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def build_benchmark_source_manifest(captures: Iterable[Mapping[str,object]], *, provider_version: str) -> dict:
    rows=[]
    for c in captures:
        for k in ("game_id","book","source_identifier","captured_at_utc","raw_byte_sha256","parser_code_sha256"):
            if c.get(k) in (None,""): raise ValueError(f"{k} required")
        rows.append({"game_id":str(c["game_id"]),"book":str(c["book"]),"source_identifier":str(c["source_identifier"]),"captured_at_utc":_utc(c["captured_at_utc"]),"raw_byte_sha256":_sha(c["raw_byte_sha256"],"raw_byte_sha256"),"parser_code_sha256":_sha(c["parser_code_sha256"],"parser_code_sha256")})
    if not rows or not str(provider_version).strip(): raise ValueError("captures and provider version required")
    rows.sort(key=lambda x:(x["game_id"],x["book"],x["captured_at_utc"]))
    out={"schema":SCHEMA,"provider_version":str(provider_version),"role":"EVALUATION_COMPARATOR_ONLY","sportsbook_inputs_allowed_in_model_fit":False,"captures":rows,"model_p_authority":False,"promotion_authority":False,"official_authority":False}
    out["manifest_sha256"]=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":")).encode()).hexdigest(); return out
