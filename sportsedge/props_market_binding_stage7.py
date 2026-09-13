"""Stage 7 prop market binding.

This adapter can price a posted market only after an independently validated
probability exists. It never creates Model_P from sportsbook prices.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Optional

STATUS_RESEARCH="RESEARCH_ONLY_POST_VALIDATION_BINDING"
NO_VIG_ONE_SIDED="UNAVAILABLE_ONE_SIDED"

def _american_odds(value:object,name:str="odds")->int:
    if isinstance(value,bool) or not isinstance(value,int):
        raise ValueError(f"BAD_AMERICAN_ODDS_TYPE:{name}")
    if -99<=value<=99:
        raise ValueError(f"BAD_AMERICAN_ODDS_RANGE:{name}")
    return value

def _market_line(value:object|None)->float|None:
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValueError("BAD_MARKET_LINE_TYPE")
    line=float(value)
    if not isfinite(line):raise ValueError("BAD_MARKET_LINE_NONFINITE")
    return line

def american_to_decimal(odds:int)->float:
    odds=_american_odds(odds)
    return 1.0+((100.0/abs(odds)) if odds<0 else (odds/100.0))

def raw_implied_probability(odds:int)->float:
    return 1.0/american_to_decimal(odds)

def probability_to_fair_american(p:float)->int:
    try:p=float(p)
    except (TypeError,ValueError) as exc:raise ValueError("FAIR_ODDS_REQUIRES_INTERIOR_PROBABILITY") from exc
    if not isfinite(p) or not 0<p<1: raise ValueError("FAIR_ODDS_REQUIRES_INTERIOR_PROBABILITY")
    return round(-100*p/(1-p)) if p>=.5 else round(100*(1-p)/p)

def proportional_devig(a:int,b:int)->tuple[float,float]:
    a=_american_odds(a,"side_a");b=_american_odds(b,"side_b")
    pa,pb=raw_implied_probability(a),raw_implied_probability(b); s=pa+pb
    if not isfinite(s) or s<=0:raise ValueError("BAD_TWO_SIDED_MARKET")
    return pa/s,pb/s

@dataclass(frozen=True)
class BoundProp:
    sport:str; market:str; entity_id:str; line:Optional[float]; model_probability:float
    fair_american_odds:int; offered_odds:int; decimal_odds:float; expected_value_per_unit:float
    market_no_vig_probability:float|str; validation_passed:bool
    status:str=STATUS_RESEARCH; official:bool=False; staking_authority:bool=False

def bind_prop_market(*,sport:str,market:str,entity_id:str,model_probability:float,offered_odds:int,validation_passed:bool,line:float|None=None,paired_other_side_odds:int|None=None)->BoundProp:
    if validation_passed is not True:raise ValueError("BLOCKED_NO_VALIDATED_PROBABILITY_ENGINE")
    try:p=float(model_probability)
    except (TypeError,ValueError) as exc:raise ValueError("BAD_MODEL_PROBABILITY") from exc
    if not isfinite(p) or not 0<p<1:raise ValueError("BAD_MODEL_PROBABILITY")
    offered=_american_odds(offered_odds,"offered_odds")
    paired=None if paired_other_side_odds is None else _american_odds(paired_other_side_odds,"paired_other_side_odds")
    bound_line=_market_line(line)
    dec=american_to_decimal(offered); ev=p*(dec-1.0)-(1.0-p)
    nv:float|str=NO_VIG_ONE_SIDED if paired is None else proportional_devig(offered,paired)[0]
    return BoundProp(sport,market,entity_id,bound_line,p,probability_to_fair_american(p),offered,dec,ev,nv,True)
