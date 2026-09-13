"""Frozen four-family CFB candidate registry. No evaluation authority."""
from .candidate_families import TEAM_METRIC_KEYS, materialize_equal_weight_hard_switch, _assert_market_blind, CFBCandidateFamilyError
from .candidate_variants import reliability_hard_switch, prior_current_blend, games_in_sample_feature

EQUAL="EQUAL_WEIGHT_HARD_SWITCH"
RELIABILITY="RELIABILITY_WEIGHTED_HARD_SWITCH"
BLEND="PRIOR_CURRENT_BLEND"
GAMES="GAMES_IN_SAMPLE_FEATURE"
IMPLEMENTED_FAMILIES=frozenset({EQUAL,RELIABILITY,BLEND,GAMES})

def materialize_candidate_row(family,row,constants=None):
    if constants not in (None,{}):
        raise CFBCandidateFamilyError("CFB_CANDIDATE_RUNTIME_CONSTANT_OVERRIDE_PROHIBITED")
    _assert_market_blind({k:v for k,v in row.items() if k not in {"home_score","away_score","regulation_home_score","regulation_away_score"}})
    try:
        if family==EQUAL: return materialize_equal_weight_hard_switch(row)
        if family==RELIABILITY: return reliability_hard_switch(row,TEAM_METRIC_KEYS)
        if family==BLEND: return prior_current_blend(row,TEAM_METRIC_KEYS)
        if family==GAMES: return games_in_sample_feature(row,TEAM_METRIC_KEYS)
    except ValueError as exc:
        raise CFBCandidateFamilyError(str(exc)) from exc
    raise CFBCandidateFamilyError(f"CFB_CANDIDATE_FAMILY_UNIMPLEMENTED:{family}")
