"""NFL V2K PIT fit/binding contract.

Research only: no Model_P, promotion, staking, or OFFICIAL authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping
import hashlib, json, math
from .v2k_drive_simulator import DriveOutcome, V2KParams, START_BINS, start_bin
FIT_SCHEMA="SPORTSEDGE_NFL_V2K_PIT_FIT_V1"

@dataclass(frozen=True)
class DriveRow:
    game_id: str
    kickoff_utc: str
    offense: str
    start_yard: float
    outcome: str

def _dt(value: str) -> datetime:
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("timestamp must be timezone-aware")
    return d.astimezone(timezone.utc)

def _prob_map(counts: Mapping[str,int], n: int, fallback: Mapping[str,float] | None=None) -> dict[str,float]:
    if n<=0:
        if fallback is None: raise ValueError("empty outcome sample without fallback")
        return {k:float(v) for k,v in fallback.items()}
    return {k:int(counts[k])/n for k in counts}

def fit_pit(rows: Iterable[DriveRow], *, prediction_cutoff_utc: str, source_manifest_sha256: str, feature_policy_sha256: str, code_sha: str) -> dict:
    cutoff=_dt(prediction_cutoff_utc); accepted=[]; taxonomy={x.value for x in DriveOutcome}
    for r in rows:
        if _dt(r.kickoff_utc)>=cutoff: raise ValueError("PIT violation: training row at/after prediction cutoff")
        if not r.game_id or not r.offense: raise ValueError("game/offense identity required")
        if r.outcome not in taxonomy: raise ValueError("unknown drive outcome")
        if not 1.0<=float(r.start_yard)<=99.0: raise ValueError("invalid starting field position")
        accepted.append(r)
    if not accepted: raise ValueError("no PIT-safe training rows")
    if len(source_manifest_sha256)!=64: raise ValueError("missing immutable source manifest identity")
    if len(feature_policy_sha256)!=64: raise ValueError("missing immutable feature policy identity")
    if len(code_sha)<7: raise ValueError("missing immutable code identity")
    counts={x.value:0 for x in DriveOutcome}; bin_counts={b:{x.value:0 for x in DriveOutcome} for b in START_BINS}; bin_n={b:0 for b in START_BINS}
    starts=[]; possessions={}; game_scoring={}
    for r in accepted:
        counts[r.outcome]+=1; starts.append(float(r.start_yard)); b=start_bin(r.start_yard); bin_counts[b][r.outcome]+=1; bin_n[b]+=1
        key=(r.game_id,r.offense); possessions[key]=possessions.get(key,0)+1
        gs=game_scoring.setdefault(r.game_id,[0,0]); gs[1]+=1
        if r.outcome in (DriveOutcome.TD.value,DriveOutcome.FG.value): gs[0]+=1
    n=len(accepted); global_probs=_prob_map(counts,n); mean_start=sum(starts)/n
    var_start=sum((x-mean_start)**2 for x in starts)/max(1,n-1)
    drive_counts=list(possessions.values()); mean_drives=sum(drive_counts)/len(drive_counts)
    var_drives=sum((x-mean_drives)**2 for x in drive_counts)/max(1,len(drive_counts)-1)
    logits=[]
    for scoring,total in game_scoring.values():
        p=(scoring+0.5)/(total+1.0); logits.append(math.log(p/(1.0-p)))
    mean_logit=sum(logits)/len(logits); shared_sd=(sum((x-mean_logit)**2 for x in logits)/max(1,len(logits)-1))**0.5
    by_bin={b:_prob_map(bin_counts[b],bin_n[b],global_probs) for b in START_BINS}
    fit={"schema":FIT_SCHEMA,"prediction_cutoff_utc":cutoff.isoformat(),"source_manifest_sha256":source_manifest_sha256,"feature_policy_sha256":feature_policy_sha256,"code_sha":code_sha,"training_rows":n,"training_team_games":len(possessions),"training_games":len(game_scoring),"params":{"drives_mean":mean_drives,"drives_sd":var_drives**0.5,"start_yard_mean":mean_start,"start_yard_sd":var_start**0.5,"shared_efficiency_sd":shared_sd,"outcome_probs":global_probs,"outcome_probs_by_start_bin":by_bin},"model_p_authority":False,"promotion_authority":False,"official_authority":False}
    canonical=json.dumps(fit,sort_keys=True,separators=(",",":")).encode(); fit["fit_sha256"]=hashlib.sha256(canonical).hexdigest(); return fit

def params_from_fit(fit: Mapping, *, expected_source_manifest_sha256: str, expected_feature_policy_sha256: str, expected_code_sha: str) -> V2KParams:
    if fit.get("schema")!=FIT_SCHEMA: raise ValueError("fit schema mismatch")
    if fit.get("source_manifest_sha256")!=expected_source_manifest_sha256: raise ValueError("train/serve source manifest mismatch")
    if fit.get("feature_policy_sha256")!=expected_feature_policy_sha256: raise ValueError("train/serve feature policy mismatch")
    if fit.get("code_sha")!=expected_code_sha: raise ValueError("train/serve code SHA mismatch")
    if any(bool(fit.get(k)) for k in ("model_p_authority","promotion_authority","official_authority")): raise ValueError("research fit cannot carry bettor-facing authority")
    p=fit["params"]
    if "shared_efficiency_sd" not in p or "outcome_probs_by_start_bin" not in p: raise ValueError("fit missing preregistered generative parameters")
    return V2KParams(drives_mean=float(p["drives_mean"]),drives_sd=float(p["drives_sd"]),start_yard_mean=float(p["start_yard_mean"]),start_yard_sd=float(p["start_yard_sd"]),shared_efficiency_sd=float(p["shared_efficiency_sd"]),outcome_probs=dict(p["outcome_probs"]),outcome_probs_by_start_bin={k:dict(v) for k,v in p["outcome_probs_by_start_bin"].items()})
