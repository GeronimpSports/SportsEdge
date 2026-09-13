"""Chronological/walk-forward validation gate for prop probability engines.
Passing this research gate does not itself grant production/promotion authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, log, sqrt
from typing import Iterable, Mapping

@dataclass(frozen=True)
class ValidationResult:
    n:int; brier:float; log_loss:float; mae:float; rmse:float; ece:float; max_bin_deviation:float
    calibration_slope:float; calibration_intercept:float; chronological:bool; passed:bool; authority:str="RESEARCH_ONLY"

def _ols_calibration(ps:list[float],ys:list[float])->tuple[float,float]:
    mp=sum(ps)/len(ps); my=sum(ys)/len(ys); var=sum((p-mp)**2 for p in ps)
    slope=(sum((p-mp)*(y-my) for p,y in zip(ps,ys))/var) if var>1e-12 else 0.0
    intercept=my-slope*mp
    return slope,intercept

def _event_time(value:object)->datetime:
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError) as exc:
        raise ValueError("VALIDATION_TIMESTAMP_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("VALIDATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt

def validate_probability_rows(rows:Iterable[Mapping[str,object]],*,min_n:int=200,ece_max:float=.025,max_bin_deviation_max:float=.05,slope_min:float=.90,slope_max:float=1.10,intercept_abs_max:float=.03)->ValidationResult:
    xs=list(rows)
    if not xs: raise ValueError("NO_VALIDATION_ROWS")
    times=[_event_time(r["event_start_ts"]) for r in xs]
    if times!=sorted(times): raise ValueError("NON_CHRONOLOGICAL_VALIDATION_FORBIDDEN")
    probability_rows=[]; ys=[]
    quantity_mode=any("quantity_prediction" in r or "quantity_actual" in r for r in xs)
    quantities=[]
    for r in xs:
        try:
            p=float(r["model_probability"]); y=float(r["outcome"])
        except (TypeError,ValueError,KeyError) as exc:
            raise ValueError("BAD_PROBABILITY_ROW") from exc
        if not isfinite(p) or not isfinite(y) or not 0<=p<=1 or y not in {0.0,1.0}: raise ValueError("BAD_PROBABILITY_ROW")
        probability_rows.append(p);ys.append(y)
        if quantity_mode:
            if "quantity_prediction" not in r or "quantity_actual" not in r:
                raise ValueError("INCOMPLETE_QUANTITY_VALIDATION_ROW")
            try:
                prediction=float(r["quantity_prediction"]); actual=float(r["quantity_actual"])
            except (TypeError,ValueError) as exc:
                raise ValueError("BAD_QUANTITY_VALIDATION_ROW") from exc
            if not isfinite(prediction) or not isfinite(actual): raise ValueError("BAD_QUANTITY_VALIDATION_ROW")
            quantities.append((prediction,actual))
    n=len(xs)
    brier=sum((p-y)**2 for p,y in zip(probability_rows,ys))/n
    log_ps=[min(1-1e-12,max(1e-12,p)) for p in probability_rows]
    ll=-sum(y*log(p)+(1-y)*log(1-p) for p,y in zip(log_ps,ys))/n
    bins=[[] for _ in range(10)]
    for p,y in zip(probability_rows,ys): bins[min(9,int(p*10))].append((p,y))
    ece=0.; maxdev=0.
    for b in bins:
        if not b: continue
        mp=sum(x for x,_ in b)/len(b); my=sum(y for _,y in b)/len(b); dev=abs(mp-my); ece+=len(b)/n*dev; maxdev=max(maxdev,dev)
    slope,intercept=_ols_calibration(probability_rows,ys)
    if quantities:
        mae=sum(abs(a-b) for a,b in quantities)/len(quantities); rmse=sqrt(sum((a-b)**2 for a,b in quantities)/len(quantities))
    else: mae=rmse=float("nan")
    passed=(n>=min_n and ece<=ece_max and maxdev<=max_bin_deviation_max and slope_min<=slope<=slope_max and abs(intercept)<=intercept_abs_max)
    return ValidationResult(n,brier,ll,mae,rmse,ece,maxdev,slope,intercept,True,passed)
