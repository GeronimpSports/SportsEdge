"""Stage 7 prop market binding.

This adapter can price a posted market only after an independently validated
probability exists. It never creates Model_P from sportsbook prices.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

STATUS_RESEARCH="RESEARCH_ONLY_POST_VALIDATION_BINDING"
NO_VIG_ONE_SIDED="UNAVAILABLE_ONE_SIDED"

def american_to_decimal(odds:int)->float:
    if odds==0: raise ValueError("BAD_AMERICAN_ODDS")
    return 1.0+((100.0/abs(odds)) if odds<0 else (odds/100.0))

def raw_implied_probability(odds:int)->float:
    return 1.0/american_to_decimal(odds)

def probability_to_fair_american(p:float)->int:
    p=float(p)
    if not 0<p<1: raise ValueError("FAIR_ODDS_REQUIRES_INTERIOR_PROBABILITY")
    return round(-100*p/(1-p)) if p>=.5 else round(100*(1-p)/p)

def proportional_devig(a:int,b:int)->tuple[float,float]:
    pa,pb=raw_implied_probability(a),raw_implied_probability(b); s=pa+pb
    if s<=0:raise ValueError("BAD_TWO_SIDED_MARKET")
    return pa/s,pb/s

@dataclass(frozen=True)
class BoundProp:
    sport:str; market:str; entity_id:str; line:Optional[float]; model_probability:float
    fair_american_odds:int; offered_odds:int; decimal_odds:float; expected_value_per_unit:float
    market_no_vig_probability:float|str; validation_passed:bool
    status:str=STATUS_RESEARCH; official:bool=False; staking_authority:bool=False

def bind_prop_market(*,sport:str,market:str,entity_id:str,model_probability:float,offered_odds:int,validation_passed:bool,line:float|None=None,paired_other_side_odds:int|None=None)->BoundProp:
    if not validation_passed:raise ValueError("BLOCKED_NO_VALIDATED_PROBABILITY_ENGINE")
    p=float(model_probability)
    if not 0<p<1:raise ValueError("BAD_MODEL_PROBABILITY")
    dec=american_to_decimal(int(offered_odds)); ev=p*(dec-1.0)-(1.0-p)
    nv:float|str=NO_VIG_ONE_SIDED if paired_other_side_odds is None else proportional_devig(int(offered_odds),int(paired_other_side_odds))[0]
    return BoundProp(sport,market,entity_id,line,p,probability_to_fair_american(p),int(offered_odds),dec,ev,nv,True)
