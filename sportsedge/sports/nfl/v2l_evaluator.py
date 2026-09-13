"""Fail-closed V2L evaluator using provenance-bound M1 evidence.
Research-only; grants no betting authority.
"""
from __future__ import annotations
from typing import Mapping, Sequence
import hashlib, json
from .v2l_benchmark import SCHEMA as BENCHMARK_SCHEMA, fold_joint_score_rmse

KEYS=(-7,-3,3,7)

def evaluate_v2l(*, policy: Mapping, calibration: Mapping[str,float], key_empirical: Mapping[int,float],
                 key_simulated: Mapping[int,float], fold_candidate_rmse: Sequence[float],
                 fold_game_ids: Sequence[Sequence[str]], actual_scores: Mapping[str,Sequence[float]],
                 benchmark_evidence: Mapping[str,object], sample_n: int, code_sha: str,
                 source_manifest_sha256: str, fit_sha256: str, distribution_sha256: str,
                 benchmark_policy_sha256: str) -> dict:
    if policy.get("status")!="FROZEN_BEFORE_FIRST_READOUT": raise ValueError("evaluation policy not frozen")
    if benchmark_evidence.get("schema")!=BENCHMARK_SCHEMA: raise ValueError("bound benchmark evidence required")
    if str(benchmark_evidence.get("benchmark_policy_sha256"))!=str(benchmark_policy_sha256).lower(): raise ValueError("benchmark policy identity mismatch")
    evidence_sha=str(benchmark_evidence.get("benchmark_evidence_sha256") or "")
    manifest_sha=str(benchmark_evidence.get("benchmark_source_manifest_sha256") or "")
    if len(evidence_sha)!=64 or len(manifest_sha)!=64: raise ValueError("benchmark evidence lineage required")
    if len(fold_candidate_rmse)!=len(fold_game_ids) or not fold_candidate_rmse: raise ValueError("fold alignment required")
    if len(code_sha)<7 or any(len(str(x))!=64 for x in (source_manifest_sha256,fit_sha256,distribution_sha256,benchmark_policy_sha256)): raise ValueError("immutable evidence identities required")
    predictive=policy.get("predictive")
    if not isinstance(predictive,Mapping): raise ValueError("frozen predictive policy required")
    required_reports=("must_report_score_rmse","must_report_margin_rmse","must_report_total_rmse","must_report_brier","must_report_log_loss","must_report_fold_stability")
    if any(not bool(predictive.get(k)) for k in required_reports): raise ValueError("complete frozen reporting contract required")
    if not bool(predictive.get("pass_requires_frozen_benchmark_rule")): raise ValueError("frozen benchmark rule required")
    if bool(predictive.get("ties_are_wins")): raise ValueError("strict fold improvement required")
    min_rate=float(predictive["minimum_fold_win_rate"]); min_wins=int(predictive["minimum_fold_wins"])
    baselines=[fold_joint_score_rmse(evidence=benchmark_evidence,game_ids=list(ids),actual_scores=actual_scores) for ids in fold_game_ids]
    cal_cfg=policy["calibration"]
    cal_pass=(sample_n>=int(policy["minimum_calibration_n"]) and cal_cfg["slope_min"]<=float(calibration["slope"])<=cal_cfg["slope_max"] and abs(float(calibration["intercept"]))<=cal_cfg["intercept_abs_max"] and float(calibration["ece"])<=cal_cfg["ece_max"])
    errors={str(k):abs(float(key_simulated[k])-float(key_empirical[k])) for k in KEYS}
    key_pass=all(v<=float(policy["signed_key_margin"]["max_abs_error_each"]) for v in errors.values())
    wins=sum(float(c)<float(b) for c,b in zip(fold_candidate_rmse,baselines)); n=len(baselines); rate=wins/n
    predictive_pass=wins>=min_wins and rate>=min_rate
    passed=bool(cal_pass and key_pass and predictive_pass)
    out={"schema":"SPORTSEDGE_NFL_V2L_FIRST_READOUT_EVAL_V1","result":"PASS" if passed else "FAIL","model_validity_pass":passed,
         "calibration_pass":cal_pass,"key_number_pass":key_pass,"predictive_pass":predictive_pass,"fold_wins":wins,"fold_count":n,"fold_win_rate":rate,
         "fold_baseline_rmse":baselines,"signed_key_abs_error":errors,"code_sha":code_sha,"source_manifest_sha256":source_manifest_sha256,
         "fit_sha256":fit_sha256,"distribution_sha256":distribution_sha256,"benchmark_policy_sha256":str(benchmark_policy_sha256).lower(),
         "benchmark_source_manifest_sha256":manifest_sha,"benchmark_evidence_sha256":evidence_sha,
         "model_p_authority":False,"promotion_authority":False,"official_authority":False}
    raw=json.dumps(out,sort_keys=True,separators=(",",":")).encode(); out["evaluation_sha256"]=hashlib.sha256(raw).hexdigest(); return out
