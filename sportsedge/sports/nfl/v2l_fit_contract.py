"""NFL V2L matchup-specific PIT fit/serve contract.

Research only. No Model_P, promotion, staking, or OFFICIAL authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping
import hashlib, json, math
from .v2k_drive_simulator import DriveOutcome, V2KParams, START_BINS, start_bin

FIT_SCHEMA="SPORTSEDGE_NFL_V2L_MATCHUP_FIT_V1"
MIN_UNSHRUNK_DRIVES=200
PRIOR_DRIVES=200.0

@dataclass(frozen=True)
class DriveRow:
    game_id: str
    kickoff_utc: str
    offense: str
    defense: str
    start_yard: float
    outcome: str

def _dt(value: str) -> datetime:
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return d.astimezone(timezone.utc)

def _logit(p: float) -> float:
    p=min(max(float(p),1e-9),1.0-1e-9)
    return math.log(p/(1.0-p))

def _sigmoid(x: float) -> float:
    return 1.0/(1.0+math.exp(-x))

def _shrunk_rate(successes: int, n: int, league_rate: float) -> float:
    if n <= 0:
        return league_rate
    # Frozen feature policy permits unshrunk team use only once 200 drives are
    # available. Below that threshold retain the preregistered league-mean
    # empirical-Bayes shrinkage; at/above it use the observed team rate.
    if n >= MIN_UNSHRUNK_DRIVES:
        return float(successes)/float(n)
    return (successes + PRIOR_DRIVES*league_rate)/(n + PRIOR_DRIVES)

def _prob_map(counts: Mapping[str,int], n: int) -> dict[str,float]:
    return {k:int(v)/n for k,v in counts.items()}

def _shrunk_pace(total_drives: int, games: int, league_mean: float) -> float:
    if games <= 0:
        return league_mean
    if total_drives >= MIN_UNSHRUNK_DRIVES:
        return float(total_drives)/float(games)
    prior_games=PRIOR_DRIVES/max(league_mean,1e-9)
    return (float(total_drives)+prior_games*league_mean)/(float(games)+prior_games)

def fit_pit(rows: Iterable[DriveRow], *, prediction_cutoff_utc: str, source_manifest_sha256: str, feature_policy_sha256: str, code_sha: str) -> dict:
    cutoff=_dt(prediction_cutoff_utc)
    taxonomy={x.value for x in DriveOutcome}
    accepted=[]
    for r in rows:
        if _dt(r.kickoff_utc)>=cutoff:
            raise ValueError("PIT violation: training row at/after prediction cutoff")
        if not r.game_id or not r.offense or not r.defense:
            raise ValueError("game/offense/defense identity required")
        if r.outcome not in taxonomy:
            raise ValueError("unknown drive outcome")
        if not 1.0<=float(r.start_yard)<=99.0:
            raise ValueError("invalid starting field position")
        accepted.append(r)
    if not accepted:
        raise ValueError("no PIT-safe training rows")
    if len(source_manifest_sha256)!=64 or len(feature_policy_sha256)!=64 or len(code_sha)<7:
        raise ValueError("missing immutable identity")

    outcome_counts={x.value:0 for x in DriveOutcome}
    bin_counts={b:{x.value:0 for x in DriveOutcome} for b in START_BINS}
    bin_n={b:0 for b in START_BINS}
    starts=[]; possessions={}; defense_possessions={}; game_scoring={}; off={}; deff={}
    for r in accepted:
        scoring=int(r.outcome in (DriveOutcome.TD.value,DriveOutcome.FG.value))
        outcome_counts[r.outcome]+=1
        b=start_bin(r.start_yard); bin_counts[b][r.outcome]+=1; bin_n[b]+=1
        starts.append(float(r.start_yard))
        possessions[(r.game_id,r.offense)]=possessions.get((r.game_id,r.offense),0)+1
        defense_possessions[(r.game_id,r.defense)]=defense_possessions.get((r.game_id,r.defense),0)+1
        gs=game_scoring.setdefault(r.game_id,[0,0]); gs[0]+=scoring; gs[1]+=1
        os=off.setdefault(r.offense,[0,0]); os[0]+=scoring; os[1]+=1
        ds=deff.setdefault(r.defense,[0,0]); ds[0]+=scoring; ds[1]+=1

    n=len(accepted)
    league_scoring=sum(v[0] for v in game_scoring.values())/n
    global_probs=_prob_map(outcome_counts,n)
    by_bin={b:(_prob_map(bin_counts[b],bin_n[b]) if bin_n[b] else dict(global_probs)) for b in START_BINS}
    mean_start=sum(starts)/n
    var_start=sum((x-mean_start)**2 for x in starts)/max(1,n-1)
    drive_counts=list(possessions.values())
    mean_drives=sum(drive_counts)/len(drive_counts)
    var_drives=sum((x-mean_drives)**2 for x in drive_counts)/max(1,len(drive_counts)-1)
    logits=[]
    for scoring,total in game_scoring.values():
        p=(scoring+0.5)/(total+1.0); logits.append(_logit(p))
    mean_logit=sum(logits)/len(logits)
    shared_sd=(sum((x-mean_logit)**2 for x in logits)/max(1,len(logits)-1))**0.5
    league_logit=_logit(league_scoring)

    offense_strength={}
    for team,(scoring,total) in sorted(off.items()):
        rate=_shrunk_rate(scoring,total,league_scoring)
        offense_strength[team]={"drives":total,"scoring_rate":rate,"logit_delta":_logit(rate)-league_logit}
    defense_strength={}
    for team,(allowed,total) in sorted(deff.items()):
        rate=_shrunk_rate(allowed,total,league_scoring)
        defense_strength[team]={"drives":total,"scoring_rate_allowed":rate,"logit_delta":_logit(rate)-league_logit}

    offense_games={}; offense_drive_totals={}
    for (gid,team),cnt in possessions.items():
        offense_games[team]=offense_games.get(team,0)+1; offense_drive_totals[team]=offense_drive_totals.get(team,0)+cnt
    defense_games={}; defense_drive_totals={}
    for (gid,team),cnt in defense_possessions.items():
        defense_games[team]=defense_games.get(team,0)+1; defense_drive_totals[team]=defense_drive_totals.get(team,0)+cnt
    offense_pace={team:{"games":offense_games[team],"drives":offense_drive_totals[team],"drives_per_game":_shrunk_pace(offense_drive_totals[team],offense_games[team],mean_drives)} for team in sorted(offense_games)}
    defense_pace={team:{"games":defense_games[team],"opponent_drives":defense_drive_totals[team],"opponent_drives_per_game":_shrunk_pace(defense_drive_totals[team],defense_games[team],mean_drives)} for team in sorted(defense_games)}

    fit={
        "schema":FIT_SCHEMA,"prediction_cutoff_utc":cutoff.isoformat(),"source_manifest_sha256":source_manifest_sha256,"feature_policy_sha256":feature_policy_sha256,"code_sha":code_sha,
        "training_rows":n,"minimum_team_drives_before_unshrunk_use":MIN_UNSHRUNK_DRIVES,"prior_drives_below_threshold":PRIOR_DRIVES,"league_scoring_rate":league_scoring,
        "base_params":{"drives_mean":mean_drives,"drives_sd":var_drives**0.5,"start_yard_mean":mean_start,"start_yard_sd":var_start**0.5,"shared_efficiency_sd":shared_sd,"outcome_probs":global_probs,"outcome_probs_by_start_bin":by_bin},
        "offense_strength":offense_strength,"defense_strength":defense_strength,"offense_pace_strength":offense_pace,"defense_pace_strength":defense_pace,
        "model_p_authority":False,"promotion_authority":False,"official_authority":False,
    }
    canonical=json.dumps(fit,sort_keys=True,separators=(",",":")).encode(); fit["fit_sha256"]=hashlib.sha256(canonical).hexdigest(); return fit

def _team_delta(table: Mapping, team: str) -> float:
    row=table.get(team)
    return 0.0 if row is None else float(row["logit_delta"])

def _pace_for_matchup(fit: Mapping, offense: str, defense: str) -> float:
    league=float(fit["base_params"]["drives_mean"])
    off=float(fit.get("offense_pace_strength",{}).get(offense,{}).get("drives_per_game",league))
    deff=float(fit.get("defense_pace_strength",{}).get(defense,{}).get("opponent_drives_per_game",league))
    if league<=0: raise ValueError("positive league drive mean required")
    return math.exp(math.log(league)+(math.log(max(off,1e-9))-math.log(league))+(math.log(max(deff,1e-9))-math.log(league)))

def params_for_matchup(fit: Mapping, *, offense: str, defense: str, expected_source_manifest_sha256: str, expected_feature_policy_sha256: str, expected_code_sha: str) -> V2KParams:
    if fit.get("schema")!=FIT_SCHEMA: raise ValueError("fit schema mismatch")
    if fit.get("source_manifest_sha256")!=expected_source_manifest_sha256 or fit.get("feature_policy_sha256")!=expected_feature_policy_sha256 or fit.get("code_sha")!=expected_code_sha: raise ValueError("train/serve immutable identity mismatch")
    if not offense or not defense: raise ValueError("offense and defense required")
    if any(bool(fit.get(k)) for k in ("model_p_authority","promotion_authority","official_authority")): raise ValueError("research fit cannot carry bettor-facing authority")
    base=fit["base_params"]
    delta=_team_delta(fit["offense_strength"],offense)+_team_delta(fit["defense_strength"],defense)
    league=float(fit["league_scoring_rate"]); target=_sigmoid(_logit(league)+delta); scale=target/league if league>0 else 1.0
    scoring={DriveOutcome.TD.value,DriveOutcome.FG.value}; probs=dict(base["outcome_probs"])
    for k in probs:
        if k in scoring: probs[k]*=scale
    z=sum(probs.values()); probs={k:v/z for k,v in probs.items()}
    by_bin={}
    for b,pmap in base["outcome_probs_by_start_bin"].items():
        q=dict(pmap)
        for k in q:
            if k in scoring: q[k]*=scale
        s=sum(q.values()); by_bin[b]={k:v/s for k,v in q.items()}
    return V2KParams(drives_mean=_pace_for_matchup(fit,offense,defense),drives_sd=float(base["drives_sd"]),start_yard_mean=float(base["start_yard_mean"]),start_yard_sd=float(base["start_yard_sd"]),shared_efficiency_sd=float(base["shared_efficiency_sd"]),outcome_probs=probs,outcome_probs_by_start_bin=by_bin)
