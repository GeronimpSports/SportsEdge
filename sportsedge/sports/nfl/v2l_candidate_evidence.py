"""Immutable per-game prediction evidence for the V2L one-shot screen.

Construction emits no evaluation statistic. Research only.
"""
from __future__ import annotations
import hashlib, json, math
from typing import Mapping, Sequence

SCHEMA="SPORTSEDGE_NFL_V2L_CANDIDATE_PREDICTION_EVIDENCE_V1"

def _sha64(v: object, label: str) -> str:
    s=str(v or "")
    if len(s)!=64 or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"{label} must be SHA256")
    return s.lower()

def build_candidate_prediction_evidence(*, rows: Sequence[Mapping[str,object]], candidate_identity_sha256: str,
                                        source_manifest_sha256: str, fit_sha256: str,
                                        readout_policy_sha256: str) -> dict:
    if not rows:
        raise ValueError("candidate prediction rows required")
    out_rows=[]; seen=set()
    for r in rows:
        gid=str(r.get("game_id") or "").strip()
        if not gid or gid in seen:
            raise ValueError("unique game_id required")
        seen.add(gid)
        season=int(r.get("season"))
        if season!=2020:
            raise ValueError("only frozen untouched 2020 rows may enter candidate evidence")
        home=float(r.get("home_score_mean")); away=float(r.get("away_score_mean"))
        if not math.isfinite(home) or not math.isfinite(away) or home<0 or away<0:
            raise ValueError("finite nonnegative score means required")
        out_rows.append({
            "game_id":gid,"season":season,
            "home_score_mean":home,"away_score_mean":away,
            "bound_distribution_sha256":_sha64(r.get("bound_distribution_sha256"),"bound_distribution_sha256"),
        })
    out_rows.sort(key=lambda x:x["game_id"])
    out={
        "schema":SCHEMA,"candidate_identity_sha256":_sha64(candidate_identity_sha256,"candidate_identity_sha256"),
        "source_manifest_sha256":_sha64(source_manifest_sha256,"source_manifest_sha256"),
        "fit_sha256":_sha64(fit_sha256,"fit_sha256"),
        "readout_policy_sha256":_sha64(readout_policy_sha256,"readout_policy_sha256"),
        "rows":out_rows,"model_p_authority":False,"promotion_authority":False,"official_authority":False,
    }
    raw=json.dumps(out,sort_keys=True,separators=(",",":")).encode()
    out["candidate_evidence_sha256"]=hashlib.sha256(raw).hexdigest()
    return out

def joint_score_rmse(*, evidence: Mapping[str,object], game_ids: Sequence[str], actual_scores: Mapping[str,Sequence[float]]) -> float:
    if evidence.get("schema")!=SCHEMA:
        raise ValueError("candidate evidence schema mismatch")
    by={str(r["game_id"]):r for r in evidence.get("rows",[])}
    if not game_ids:
        raise ValueError("fold game ids required")
    sq=[]
    for gid in game_ids:
        if gid not in by or gid not in actual_scores:
            raise ValueError("complete candidate fold lineage required")
        a=actual_scores[gid]
        if len(a)!=2:
            raise ValueError("home/away actual score pair required")
        r=by[gid]
        sq.extend([(float(r["home_score_mean"])-float(a[0]))**2,(float(r["away_score_mean"])-float(a[1]))**2])
    return (sum(sq)/len(sq))**0.5
