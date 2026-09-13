import pytest
from sportsedge.sports.nfl.v2l_benchmark import build_m1_benchmark
from sportsedge.sports.nfl.v2l_evaluator import evaluate_v2l

S="a"*64; F="b"*64; D="c"*64; P="d"*64; M="e"*64; C="1"*64; E="2"*64; R="3"*64

def policy():
    return {"schema":"SPORTSEDGE_NFL_V2L_EVAL_POLICY_V1","status":"FROZEN_BEFORE_FIRST_READOUT","untouched_evaluation_seasons":[2020],"minimum_calibration_n":1,
      "calibration":{"slope_min":.9,"slope_max":1.1,"intercept_abs_max":.03,"ece_max":.05},
      "signed_key_margin":{"max_abs_error_each":.005},
      "predictive":{"must_report_score_rmse":True,"must_report_margin_rmse":True,"must_report_total_rmse":True,"must_report_brier":True,"must_report_log_loss":True,"must_report_fold_stability":True,"pass_requires_frozen_benchmark_rule":True,"minimum_fold_win_rate":1.0,"minimum_fold_wins":1,"ties_are_wins":False,"bootstrap_required":True,"bootstrap_resamples":100,"bootstrap_seed":20260913}}

def readout():
    return {"schema":"SPORTSEDGE_NFL_V2L_FIRST_READOUT_POLICY_V1","status":"FROZEN_BEFORE_FIRST_READOUT","evaluation_seasons":[2020]}

def evidence():
    c={"game_id":"g1","captured_at_utc":"2025-09-01T12:00:00+00:00","kickoff_utc":"2025-09-01T17:00:00+00:00","home_ml":-120,"away_ml":110,"home_spread":-2.5,"game_total":44.5,"capture_sha256":"f"*64}
    return build_m1_benchmark(captures=[c],benchmark_policy_sha256=P,benchmark_source_manifest_sha256=M)

def args():
    z={k:0.1 for k in (-7,-3,3,7)}
    return dict(policy=policy(),first_readout_policy=readout(),calibration={"slope":1,"intercept":0,"ece":.01},key_empirical=z,key_simulated=z,
      fold_candidate_rmse=[1.0],fold_candidate_game_sqerr=[[1.0]],fold_game_ids=[["g1"]],actual_scores={"g1":[24,20]},benchmark_evidence=evidence(),sample_n=10,
      code_sha="1234567",source_manifest_sha256=S,fit_sha256=F,distribution_sha256=D,candidate_identity_sha256=C,eval_policy_sha256=E,first_readout_policy_sha256=R,benchmark_policy_sha256=P)

def test_baseline_is_derived_from_bound_evidence():
    out=evaluate_v2l(**args())
    assert len(out["fold_baseline_rmse"])==1
    assert out["benchmark_evidence_sha256"]==evidence()["benchmark_evidence_sha256"]
    assert len(out["paired_bootstrap"])==1
    assert out["model_p_authority"] is False

def test_wrong_policy_identity_blocks():
    x=args(); x["benchmark_policy_sha256"]="9"*64
    with pytest.raises(ValueError): evaluate_v2l(**x)

def test_missing_fold_capture_blocks():
    x=args(); x["fold_game_ids"]=[["missing"]]; x["actual_scores"]={"missing":[20,17]}; x["fold_candidate_game_sqerr"]=[[1.0]]
    with pytest.raises(ValueError): evaluate_v2l(**x)

def test_season_policy_mismatch_blocks():
    x=args(); x["first_readout_policy"]={"schema":"SPORTSEDGE_NFL_V2L_FIRST_READOUT_POLICY_V1","status":"FROZEN_BEFORE_FIRST_READOUT","evaluation_seasons":[2021]}
    with pytest.raises(ValueError): evaluate_v2l(**x)
