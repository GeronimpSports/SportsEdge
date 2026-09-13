"""Chronological/walk-forward validation gate for prop probability engines.
Passing this research gate does not itself grant production/promotion authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import log, sqrt
from typing import Iterable, Mapping

@dataclass(frozen=True)
class ValidationResult:
    n:int; brier:float; log_loss:float; mae:float; rmse:float; ece:float; max_bin_deviation:float; chronological:bool; passed:bool; authority:str="RESEARCH_ONLY"

def validate_probability_rows(rows:Iterable[Mapping[str,object]],*,min_n:int=200,ece_max:float=.025,max_bin_deviation_max:float=.05)->ValidationResult:
    xs=list(rows)
    if not xs: raise ValueError("NO_VALIDATION_ROWS")
    times=[str(r["event_start_ts"]) for r in xs]
    chronological=times==sorted(times)
    if not chronological: raise ValueError("NON_CHRONOLOGICAL_VALIDATION_FORBIDDEN")
    ps=[]; ys=[]; quantities=[]
    for r in xs:
        p=float(r["model_probability"]); y=float(r["outcome"])
        if not 0<=p<=1 or y not in {0.0,1.0}:raise ValueError("BAD_PROBABILITY_ROW")
        ps.append(min(1-1e-12,max(1e-12,p)));ys.append(y)
        if "quantity_prediction" in r and "quantity_actual" in r: quantities.append((float(r["quantity_prediction"]),float(r["quantity_actual"])))
    n=len(xs); brier=sum((p-y)**2 for p,y in zip(ps,ys))/n; ll=-sum(y*log(p)+(1-y)*log(1-p) for p,y in zip(ps,ys))/n
    bins=[[] for _ in range(10)]
    for p,y in zip(ps,ys): bins[min(9,int(p*10))].append((p,y))
    ece=0.; maxdev=0.
    for b in bins:
        if not b:continue
        mp=sum(x for x,_ in b)/len(b); my=sum(y for _,y in b)/len(b); dev=abs(mp-my); ece+=len(b)/n*dev; maxdev=max(maxdev,dev)
    if quantities:
        mae=sum(abs(a-b) for a,b in quantities)/len(quantities); rmse=sqrt(sum((a-b)**2 for a,b in quantities)/len(quantities))
    else: mae=rmse=float("nan")
    passed=n>=min_n and ece<=ece_max and maxdev<=max_bin_deviation_max
    return ValidationResult(n,brier,ll,mae,rmse,ece,maxdev,True,passed)
