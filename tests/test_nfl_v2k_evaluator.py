from sportsedge.sports.nfl.v2k_evaluator import evaluate_v2k

POLICY={
 "schema":"SPORTSEDGE_NFL_V2K_EVAL_POLICY_V1","status":"FROZEN_BEFORE_FIRST_READOUT","minimum_calibration_n":500,
 "calibration":{"slope_min":0.90,"slope_max":1.10,"intercept_abs_max":0.03,"ece_max":0.05},
 "signed_key_margin":{"max_abs_error_each":0.005}
}
CAL={"slope":1.0,"intercept":0.0,"ece":0.02}
EMP={-7:.03,-3:.07,3:.07,7:.03}

def test_all_gates_required_for_pass():
    sim=dict(EMP)
    r=evaluate_v2k(policy=POLICY,calibration=CAL,key_empirical=EMP,key_simulated=sim,fold_candidate_rmse=[1,1,1,1],fold_baseline_rmse=[2,2,2,2],sample_n=1000)
    assert r["result"]=="PASS"
    assert r["model_validity_pass"] is True
    assert r["model_p_authority"] is False and r["official_authority"] is False

def test_key_failure_cannot_be_rescued_by_calibration_or_prediction():
    sim=dict(EMP); sim[3]=EMP[3]+0.006
    r=evaluate_v2k(policy=POLICY,calibration=CAL,key_empirical=EMP,key_simulated=sim,fold_candidate_rmse=[1,1,1,1],fold_baseline_rmse=[2,2,2,2],sample_n=1000)
    assert r["key_number_pass"] is False and r["result"]=="FAIL"

def test_predictive_failure_is_independent_blocker():
    r=evaluate_v2k(policy=POLICY,calibration=CAL,key_empirical=EMP,key_simulated=EMP,fold_candidate_rmse=[1,3,3,1],fold_baseline_rmse=[2,2,2,2],sample_n=1000)
    assert r["predictive_pass"] is False and r["result"]=="FAIL"

def test_calibration_sample_floor_blocks():
    r=evaluate_v2k(policy=POLICY,calibration=CAL,key_empirical=EMP,key_simulated=EMP,fold_candidate_rmse=[1,1,1,1],fold_baseline_rmse=[2,2,2,2],sample_n=499)
    assert r["calibration_pass"] is False and r["result"]=="FAIL"
