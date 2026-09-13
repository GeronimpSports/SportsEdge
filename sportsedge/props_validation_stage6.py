"""Chronological/walk-forward validation gate for prop probability engines.

Passing this research gate does not itself grant production/promotion authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Mapping

@dataclass(frozen=True)
class ValidationResult:
    n:int; brier:float; log_loss:float; mae:float; rmse:float; ece:float; max_bin_deviation:float; chronological:bool; passed:bool; authority:str="RESEARCH_ONLY"

def validate_probability_rows(rows:Iterable[Mapping[str,object]],*,min_n:int=200,ece_max:float=.025,max_bin_dev:.0=0.0):
    pass
