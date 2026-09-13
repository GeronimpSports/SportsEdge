"""Separate research-only Stage 4 event engines for football TD and MLB HR."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, isfinite
from typing import Any, Mapping
from sportsedge.props_joint_stage3 import reject_market_inputs, STATUS

@dataclass(frozen=True)
class EventDistribution:
    sport:str; entity_id:str; event:str; probabilities:tuple[float,...]; status:str=STATUS
    @property
    def probability_at_least_one(self)->float:return 1.0-self.probabilities[0]

def _nonnegative_quantity(value:float,name:str)->float:
    try:
        x=float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError(f"INVALID_EVENT_QUANTITY:{name}:NOT_NUMERIC") from exc
    if not isfinite(x):raise ValueError(f"INVALID_EVENT_QUANTITY:{name}:NONFINITE")
    if x<0.0:raise ValueError(f"INVALID_EVENT_QUANTITY:{name}:NEGATIVE")
    return x

def _probability(value:float,name:str)->float:
    try:
        p=float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError(f"INVALID_EVENT_PROBABILITY:{name}:NOT_NUMERIC") from exc
    if not isfinite(p):raise ValueError(f"INVALID_EVENT_PROBABILITY:{name}:NONFINITE")
    if p<0.0 or p>1.0:raise ValueError(f"INVALID_EVENT_PROBABILITY:{name}:OUT_OF_RANGE")
    return p

def _poisson(lam:float,cap:int=5)->tuple[float,...]:
    lam=_nonnegative_quantity(lam,"poisson_intensity")
    if lam==0.0:return tuple([1.0]+[0.0]*cap)
    vals=[exp(-lam)]
    for k in range(1,cap): vals.append(vals[-1]*lam/k)
    vals.append(max(0.0,1-sum(vals)))
    s=sum(vals)
    if not isfinite(s) or s<=0.0:raise ValueError("INVALID_POISSON_DISTRIBUTION")
    return tuple(v/s for v in vals)

def football_td(*,sport:str,entity_id:str,pit:Mapping[str,Any])->EventDistribution:
    reject_market_inputs(pit)
    if sport not in {"NFL","CFB"}:raise ValueError("BAD_FOOTBALL_SPORT")
    team_td=_nonnegative_quantity(pit["team_expected_touchdowns"],"team_expected_touchdowns")
    share=_probability(pit["player_td_opportunity_share"],"player_td_opportunity_share")
    availability=_probability(pit.get("availability_probability",1.0),"availability_probability")
    return EventDistribution(sport,entity_id,"touchdowns",_poisson(team_td*share*availability,4))

def mlb_hr(*,entity_id:str,pit:Mapping[str,Any])->EventDistribution:
    reject_market_inputs(pit)
    pa=_nonnegative_quantity(pit["expected_plate_appearances"],"expected_plate_appearances")
    hr_pa=_probability(pit["hr_probability_per_pa"],"hr_probability_per_pa")
    availability=_probability(pit.get("availability_probability",1.0),"availability_probability")
    return EventDistribution("MLB",entity_id,"home_runs",_poisson(pa*hr_pa*availability,4))
