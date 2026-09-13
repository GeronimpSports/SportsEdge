"""Research-only Stage 3 joint prop distributions.

Market blind by construction. This module has no Model_P, promotion, OFFICIAL,
staking, or sportsbook-binding authority until chronological validation passes.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, random
from typing import Any, Mapping

STATUS = "RESEARCH_ONLY_NO_MARKET_BINDING"
BANNED = {"odds","price","line","spread","total","sportsbook","book","market","closing_line","opening_line","implied_probability","american_odds","decimal_odds","over_price","under_price"}

def reject_market_inputs(x: Any) -> None:
    if isinstance(x, Mapping):
        for k,v in x.items():
            key=str(k).lower()
            if key in BANNED or "sportsbook" in key or "market_price" in key or "closing_odds" in key:
                raise ValueError(f"MARKET_INPUT_FORBIDDEN:{k}")
            reject_market_inputs(v)
    elif isinstance(x,(list,tuple)):
        for v in x: reject_market_inputs(v)

def _binom(rng: random.Random, n:int, p:float)->int:
    p=min(.999,max(.001,float(p)))
    return sum(rng.random()<p for _ in range(max(0,int(n))))

def _gamma_yards(rng:random.Random,n:int,mean:float,cv:float=.65)->int:
    if n<=0:return 0
    m=max(.01,float(mean)); shape=max(.2,1/(cv*cv)); scale=m/shape
    return max(0,round(sum(rng.gammavariate(shape,scale) for _ in range(n))))

@dataclass(frozen=True)
class JointDistribution:
    sport:str; entity_id:str; paths:tuple[dict[str,int],...]; seed:int; status:str=STATUS
    @property
    def sha256(self)->str:
        raw=json.dumps(self.paths,sort_keys=True,separators=(",",":")).encode()
        return sha256(raw).hexdigest()
    def probability_over(self,metric:str,line:float)->float:
        return sum(float(p.get(metric,0))>line for p in self.paths)/len(self.paths)

def football_joint(*,sport:str,entity_id:str,volume_pmf:tuple[float,...],mode:str,efficiency:Mapping[str,float],paths:int=50000,seed:int=1)->JointDistribution:
    reject_market_inputs(efficiency)
    if sport not in {"NFL","CFB"}: raise ValueError("BAD_FOOTBALL_SPORT")
    if mode not in {"passing","receiving","rushing"}: raise ValueError("BAD_MODE")
    if paths<100: raise ValueError("TOO_FEW_PATHS")
    rng=random.Random(seed); cdf=[]; s=0.0
    for q in volume_pmf: s+=float(q); cdf.append(s)
    out=[]
    for _ in range(paths):
        u=rng.random(); n=next((i for i,c in enumerate(cdf) if u<=c),len(cdf)-1)
        if mode=="passing":
            comp=_binom(rng,n,efficiency["completion_rate"]); y=_gamma_yards(rng,n,efficiency["yards_per_attempt"])
            out.append({"pass_attempts":n,"completions":comp,"passing_yards":y})
        elif mode=="receiving":
            rec=_binom(rng,n,efficiency["catch_rate"]); y=_gamma_yards(rng,n,efficiency["yards_per_target"])
            out.append({"targets":n,"receptions":rec,"receiving_yards":y})
        else:
            y=_gamma_yards(rng,n,efficiency["yards_per_carry"])
            out.append({"rush_attempts":n,"rushing_yards":y})
    return JointDistribution(sport,entity_id,tuple(out),seed)

def mlb_joint(*,entity_id:str,opportunity_pmf:tuple[float,...],role:str,rates:Mapping[str,float],paths:int=50000,seed:int=1)->JointDistribution:
    reject_market_inputs(rates)
    if role not in {"hitter","pitcher"}: raise ValueError("BAD_MLB_ROLE")
    rng=random.Random(seed); cdf=[]; s=0.0
    for q in opportunity_pmf:s+=float(q);cdf.append(s)
    out=[]
    for _ in range(paths):
        u=rng.random(); n=next((i for i,c in enumerate(cdf) if u<=c),len(cdf)-1)
        k=_binom(rng,n,rates.get("strikeout_rate",.2)); bb=_binom(rng,max(0,n-k),rates.get("walk_rate",.08)); rem=max(0,n-k-bb); h=_binom(rng,rem,rates.get("hit_rate",.25)); xbh=_binom(rng,h,rates.get("extra_base_hit_rate",.35))
        if role=="hitter": out.append({"plate_appearances":n,"strikeouts":k,"walks":bb,"hits":h,"extra_base_hits":xbh,"total_bases":h+xbh})
        else: out.append({"batters_faced":n,"pitcher_strikeouts":k,"pitcher_walks_allowed":bb,"pitcher_hits_allowed":h})
    return JointDistribution("MLB",entity_id,tuple(out),seed)
