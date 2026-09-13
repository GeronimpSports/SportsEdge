"""Fail-closed NFL V2K first-readout evaluator. Research-only until PASS is frozen."""
from __future__ import annotations
from typing import Mapping, Sequence
import hashlib, json
KEYS=(-7,-3,3,7)

def evaluate_v2k(*, policy: Mapping, calibration: Mapping[str,float], key_empirical: Mapping[int,float], key_simulated: Mapping[int,float], fold_candidate_rmse: Sequence[float], fold_baseline_rmse: Sequence[float], sample_n: int, code_sha: str, source_manifest_sha256: str, fit_sha256: str, distribution_sha256: str) -> dict:
    if policy.get("schema")!="SPORTSEDGE_NFL_V2K_EVAL_POLICY_V1": raise ValueError("policy schema mismatch")
    if policy.get("status")!="FROZEN_BEFORE_FIRST_READOUT": raise ValueError("evaluation policy not frozen")
    if len(fold_candidate_rmse)!=len(fold_baseline_rmse) or not fold_candidate_rmse: raise ValueError("fold alignment required")
    if len(code_sha)<7 or any(len(x)!=64 for x in (source_manifest_sha256,fit_sha256,distribution_sha256)): raise ValueError("immutable evidence identities required")
    predictive_cfg=policy.get("predictive")
    if not isinstance(predictive_cfg, Mapping): raise ValueError("frozen predictive policy required")
    if "minimum_fold_win_rate" not in predictive_cfg or "minimum_fold_wins" not in predictive_cfg or "ties_are_wins" not in predictive_cfg: raise ValueError("complete frozen predictive threshold required")
    if bool(predictive_cfg["ties_are_wins"]): raise ValueError("V2K policy requires strict fold improvement")
    min_rate=float(predictive_cfg["minimum_fold_win_rate"]); min_wins=int(predictive_cfg["minimum_fold_wins"])
    if not 0.0 <= min_rate <= 1.0 or min_wins < 1: raise ValueError("invalid frozen predictive threshold")
    cal_cfg=policy["calibration"]
    cal_pass=(sample_n>=int(policy["minimum_calibration_n"]) and cal_cfg["slope_min"]<=float(calibration["slope"])<=cal_cfg["slope_max"] and abs(float(calibration["intercept"]))<=cal_cfg["intercept_abs_max"] and float(calibration["ece"])<=cal_cfg["ece_max"])
    errors={str(k):abs(float(key_simulated[k])-float(key_empirical[k])) for k in KEYS}
    key_pass=all(v<=float(policy["signed_key_margin"]["max_abs_error_each"]) for v in errors.values())
    wins=sum(float(c)<float(b) for c,b in zip(fold_candidate_rmse,fold_baseline_rmse)); fold_count=len(fold_candidate_rmse); fold_win_rate=wins/fold_count
    predictive_pass=(wins>=min_wins and fold_win_rate>=min_rate)
    passed=bool(cal_pass and key_pass and predictive_pass)
    out={"schema":"SPORTSEDGE_NFL_V2K_FIRST_READOUT_EVAL_V1","calibration_pass":cal_pass,"key_number_pass":key_pass,"predictive_pass":predictive_pass,"fold_wins":wins,"fold_count":fold_count,"fold_win_rate":fold_win_rate,"minimum_fold_wins":min_wins,"minimum_fold_win_rate":min_rate,"signed_key_abs_error":errors,"result":"PASS" if passed else "FAIL","model_validity_pass":passed,"code_sha":code_sha,"source_manifest_sha256":source_manifest_sha256,"fit_sha256":fit_sha256,"distribution_sha256":distribution_sha256,"model_p_authority":False,"promotion_authority":False,"official_authority":False}
    raw=json.dumps(out,sort_keys=True,separators=(",",":")).encode(); out["evaluation_sha256"]=hashlib.sha256(raw).hexdigest(); return out
