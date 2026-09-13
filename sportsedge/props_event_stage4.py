"""Separate research-only Stage 4 event engines for football TD and MLB HR."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp
from typing import Any, Mapping
from sportsedge.props_joint_stage3 import reject_market_inputs, STATUS

@dataclass(frozen=True)
class EventDistribution:
    sport:str; entity_id:str; event:str; probabilities:tuple[float,...]; status:str=STATUS
    @property
    def probability_at_least_one(self)->float:return 1.0-self.probabilities[0]

def _poisson(lam:float,cap:int=5)->tuple[float,...]:
    lam=max(1e-9,float(lam)); vals=[exp(-lam)];
    for k in range(1,cap): vals.append(vals[-1]*lam/k)
    vals.append(max(0.0,1-sum(vals))); s=sum(vals); return tuple(v/s for v in vals)

def football_td(*,sport:str,entity_id:str,pit:Mapping[str,Any])->EventDistribution:
    reject_market_inputs(pit)
    if sport not in {"NFL","CFB"}:raise ValueError("BAD_FOOTBALL_SPORT")
    team_td=float(pit["team_expected_touchdowns"]); share=float(pit["player_td_opportunity_share"]); availability=float(pit.get("availability_probability",1.0))
    if not 0<=share<=1 or not 0<=availability<=1:raise ValueError("BAD_TD_SHARE")
    return EventDistribution(sport,entity_id,"touchdowns",_poisson(team_td*share*availability,4))

def mlb_hr(*,entity_id:str,pit:Mapping[str,Any])->EventDistribution:
    reject_market_inputs(pit)
    pa=float(pit["expected_plate_appearances"]); hr_pa=float(pit["hr_probability_per_pa"]); availability=float(pit.get("availability_probability",1.0))
    if not 0<=hr_pa<=1 or not 0<=availability<=1:raise ValueError("BAD_HR_RATE")
    # independent PA event baseline; park/weather/pitcher/bullpen effects must already be PIT-safe in hr_probability_per_pa.
    return EventDistribution("MLB",entity_id,"home_runs",_poisson(pa*hr_pa*availability,4))
