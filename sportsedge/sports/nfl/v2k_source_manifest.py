"""Immutable source-manifest builder for NFL V2K research inputs."""
from __future__ import annotations
import hashlib, json
from typing import Iterable, Mapping
SCHEMA="SPORTSEDGE_NFL_V2K_SOURCE_MANIFEST_V1"

def build_source_manifest(files: Iterable[Mapping[str,str]], *, provider: str="nflverse/nflfastR", dataset_version: str) -> dict:
    rows=[]
    for f in files:
        name=str(f.get("name", "")); sha=str(f.get("sha256", ""))
        if not name or len(sha)!=64: raise ValueError("every raw source needs name and sha256")
        rows.append({"name":name,"sha256":sha})
    if not rows or not dataset_version: raise ValueError("source files and pinned dataset version required")
    rows=sorted(rows,key=lambda x:x["name"])
    payload={"schema":SCHEMA,"provider":provider,"dataset_version":dataset_version,"files":rows,"model_p_authority":False,"promotion_authority":False,"official_authority":False}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode(); payload["manifest_sha256"]=hashlib.sha256(raw).hexdigest(); return payload
