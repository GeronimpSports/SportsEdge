"""Fail-closed V2L evaluator using provenance-bound M1 evidence.
Research-only; grants no betting authority.
"""
from __future__ import annotations
from typing import Mapping, Sequence
import hashlib, json, math
import numpy as np
from .v2l_benchmark import SCHEMA as BENCHMARK_SCHEMA, fold_joint_score_rmse

KEYS=(-7,-3,3,7)
EVAL_SCHEMA="SPORTSEDGE_NFL_V2L_EVAL_POLICY_V1"
READOUT_SCHEMA="SPORTSEDGE_NFL_V2L_FIRST_READOUT_POLICY_V1"


def _sha64(v: object, label: str) -> str:
    s=str(v or "")
    if len(s)!=64 or any(c not in "0123456789abcdefABCDEF" for c in s): raise ValueError(f"{label} must be SHA256")
    return s.lower()


def _finite(v: object, label: str) -> float:
    try: x=float(v)
    except (TypeError,ValueError) as exc: raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(x): raise ValueError(f"{label} must be finite")
    return x


def _paired_bootstrap(candidate_game_sqerr: Sequence[float], baseline_game_sqerr: Sequence[float], *, resamples: int, seed: int) -> dict:
    if len(candidate_game_sqerr)!=len(baseline_game_sqerr) or not candidate_game_sqerr: raise ValueError("paired game errors required")
    c=np.asarray(candidate_game_sqerr,dtype=float); b=np.asarray(baseline_game_sqerr,dtype=float)
    if not np.isfinite(c).all() or not np.isfinite(b).all(): raise ValueError("finite paired game errors required")
    rng=np.random.Generator(np.random.PCG64(seed)); n=len(c); stats=np.empty(resamples,dtype=float)
    for i in range(resamples):
        idx=rng.integers(0,n,size=n)
        stats[i]=float(np.sqrt(c[idx].mean())-np.sqrt(b[idx].mean()))
    lo,hi=np.percentile(stats,[2.5,97.5])
    return {"statistic":"CANDIDATE_JOINT_SCORE_RMSE_MINUS_M1_JOINT_SCORE_RMSE","resamples":resamples,"seed":seed,"ci95":[float(lo),float(hi)]}


def evaluate_v2l(*, policy: Mapping, first_readout_policy: Mapping, calibration: Mapping[str,float], key_empirical: Mapping[int,float],
                 key_simulated: Mapping[int,float], fold_candidate_rmse: Sequence[float], fold_candidate_game_sqerr: Sequence[Sequence[float]],
                 fold_game_ids: Sequence[Sequence[str]], actual_scores: Mapping[str,Sequence[float]], benchmark_evidence: Mapping[str,object],
                 sample_n: int, code_sha: str, source_manifest_sha256: str, fit_sha256: str, distribution_sha256: str,
                 candidate_identity_sha256: str, eval_policy_sha256: str, first_readout_policy_sha256: str, benchmark_policy_sha256: str) -> dict:
    if policy.get("schema")!=EVAL_SCHEMA or policy.get("status")!="FROZEN_BEFORE_FIRST_READOUT": raise ValueError("V2L evaluation policy not frozen")
    if first_readout_policy.get("schema")!=READOUT_SCHEMA or first_readout_policy.get("status")!="FROZEN_BEFORE_FIRST_READOUT": raise ValueError("V2L first-readout policy not frozen")
    if benchmark_evidence.get("schema")!=BENCHMARK_SCHEMA: raise ValueError("bound benchmark evidence required")
    if str(benchmark_evidence.get("benchmark_policy_sha256"))!=str(benchmark_policy_sha256).lower(): raise ValueError("benchmark policy identity mismatch")
    evidence_sha=_sha64(benchmark_evidence.get("benchmark_evidence_sha256"),"benchmark_evidence_sha256")
    manifest_sha=_sha64(benchmark_evidence.get("benchmark_source_manifest_sha256"),"benchmark_source_manifest_sha256")
    identities=(source_manifest_sha256,fit_sha256,distribution_sha256,candidate_identity_sha256,eval_policy_sha256,first_readout_policy_sha256,benchmark_policy_sha256)
    [_sha64(x,"identity") for x in identities]
    if len(code_sha)<7: raise ValueError("code sha required")
    if len(fold_candidate_rmse)!=len(fold_game_ids) or len(fold_candidate_game_sqerr)!=len(fold_game_ids) or not fold_game_ids: raise ValueError("fold alignment required")
    predictive=policy.get("predictive")
    if not isinstance(predictive,Mapping): raise ValueError("frozen predictive policy required")
    required_reports=("must_report_score_rmse","must_report_margin_rmse","must_report_total_rmse","must_report_brier","must_report_log_loss","must_report_fold_stability")
    if any(not bool(predictive.get(k)) for k in required_reports): raise ValueError("complete frozen reporting contract required")
    if not bool(predictive.get("pass_requires_frozen_benchmark_rule")) or bool(predictive.get("ties_are_wins")): raise ValueError("strict frozen benchmark rule required")
    if list(policy.get("untouched_evaluation_seasons",[])) != list(first_readout_policy.get("evaluation_seasons",[])): raise ValueError("season policy mismatch")
    min_rate=float(predictive["minimum_fold_win_rate"]); min_wins=int(predictive["minimum_fold_wins"])
    baselines=[]; baseline_game_sqerr=[]
    by_game={str(r["game_id"]):r for r in benchmark_evidence.get("rows",[])}
    for ids in fold_game_ids:
        baselines.append(fold_joint_score_rmse(evidence=benchmark_evidence,game_ids=list(ids),actual_scores=actual_scores))
        fold=[]
        for gid in ids:
            if gid not in by_game or gid not in actual_scores: raise ValueError("complete benchmark game lineage required")
            r=by_game[gid]; a=actual_scores[gid]
            fold.append(((_finite(r["home_score_mean"],"home_score_mean")-_finite(a[0],"actual_home"))**2 + (_finite(r["away_score_mean"],"away_score_mean")-_finite(a[1],"actual_away"))**2)/2.0)
        baseline_game_sqerr.append(fold)
    cal_cfg=policy["calibration"]
    cal_pass=(sample_n>=int(policy["minimum_calibration_n"]) and cal_cfg["slope_min"]<=_finite(calibration["slope"],"slope")<=cal_cfg["slope_max"] and abs(_finite(calibration["intercept"],"intercept"))<=cal_cfg["intercept_abs_max"] and _finite(calibration["ece"],"ece")<=cal_cfg["ece_max"])
    errors={str(k):abs(_finite(key_simulated[k],f"simulated_{k}")-_finite(key_empirical[k],f"empirical_{k}")) for k in KEYS}
    key_pass=all(v<=float(policy["signed_key_margin"]["max_abs_error_each"]) for v in errors.values())
    wins=sum(_finite(c,"candidate_rmse")<_finite(b,"baseline_rmse") for c,b in zip(fold_candidate_rmse,baselines)); n=len(baselines); rate=wins/n
    predictive_pass=wins>=min_wins and rate>=min_rate
    boot=[]
    if predictive.get("bootstrap_required"):
        for c,b in zip(fold_candidate_game_sqerr,baseline_game_sqerr):
            boot.append(_paired_bootstrap(c,b,resamples=int(predictive["bootstrap_resamples"]),seed=int(predictive["bootstrap_seed"])))
    passed=bool(cal_pass and key_pass and predictive_pass)
    out={"schema":"SPORTSEDGE_NFL_V2L_FIRST_READOUT_EVAL_V1","result":"PASS" if passed else "FAIL","pass_semantics":"ARCHITECTURE_SCREEN_PASS_ONLY" if passed else "FROZEN_REJECTION",
         "model_validity_pass":passed,"calibration_pass":cal_pass,"key_number_pass":key_pass,"predictive_pass":predictive_pass,"fold_wins":wins,"fold_count":n,"fold_win_rate":rate,
         "fold_candidate_rmse":[float(x) for x in fold_candidate_rmse],"fold_baseline_rmse":baselines,"paired_bootstrap":boot,"signed_key_abs_error":errors,"sample_n":int(sample_n),
         "code_sha":code_sha,"source_manifest_sha256":_sha64(source_manifest_sha256,"source_manifest_sha256"),"fit_sha256":_sha64(fit_sha256,"fit_sha256"),
         "distribution_sha256":_sha64(distribution_sha256,"distribution_sha256"),"candidate_identity_sha256":_sha64(candidate_identity_sha256,"candidate_identity_sha256"),
         "eval_policy_sha256":_sha64(eval_policy_sha256,"eval_policy_sha256"),"first_readout_policy_sha256":_sha64(first_readout_policy_sha256,"first_readout_policy_sha256"),
         "benchmark_policy_sha256":_sha64(benchmark_policy_sha256,"benchmark_policy_sha256"),"benchmark_source_manifest_sha256":manifest_sha,"benchmark_evidence_sha256":evidence_sha,
         "model_p_authority":False,"promotion_authority":False,"official_authority":False}
    raw=json.dumps(out,sort_keys=True,separators=(",",":")).encode(); out["evaluation_sha256"]=hashlib.sha256(raw).hexdigest(); return out
