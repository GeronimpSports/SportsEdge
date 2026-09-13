"""Fail-closed preregistration gate for CFB model-selection attempts."""
from __future__ import annotations
import re
from typing import Any, Mapping
from .candidate_registry_v2 import IMPLEMENTED_FAMILIES
_SHA256=re.compile(r"^[0-9a-f]{64}$")
REQUIRED_SPEC_FIELDS=("formula","feature_list","weighting_blending_constants","training_window","hyperparameter_policy","source_contract_identity","code_sha256","config_sha256")
def _nonempty_string(v): return isinstance(v,str) and bool(v.strip())
def _sha(v): return isinstance(v,str) and _SHA256.fullmatch(v.strip().lower()) is not None
def _candidate_blockers(c:Mapping[str,Any],family:str):
    b=[]
    if family not in IMPLEMENTED_FAMILIES:b.append("EXECUTABLE_FAMILY_IMPLEMENTATION_MISSING")
    if c.get("family")!=family:b.append("FAMILY_IDENTITY_MISMATCH")
    if c.get("status")!="PREREGISTERED_UNEVALUATED":b.append("STATUS_MUST_BE_PREREGISTERED_UNEVALUATED")
    if not _nonempty_string(c.get("formula")):b.append("FORMULA_MISSING")
    f=c.get("feature_list")
    if not isinstance(f,list) or not f or not all(_nonempty_string(x) for x in f):b.append("FEATURE_LIST_MISSING_OR_EMPTY")
    if not isinstance(c.get("weighting_blending_constants"),Mapping):b.append("WEIGHTING_BLENDING_CONSTANTS_MISSING")
    if not isinstance(c.get("training_window"),Mapping) or not c.get("training_window"):b.append("TRAINING_WINDOW_MISSING")
    if not isinstance(c.get("hyperparameter_policy"),Mapping) or not c.get("hyperparameter_policy"):b.append("HYPERPARAMETER_POLICY_MISSING")
    if not _nonempty_string(c.get("source_contract_identity")):b.append("SOURCE_CONTRACT_IDENTITY_MISSING")
    if not _sha(c.get("code_sha256")):b.append("CODE_SHA256_MISSING_OR_INVALID")
    if not _sha(c.get("config_sha256")):b.append("CONFIG_SHA256_MISSING_OR_INVALID")
    if any(k in c for k in {"selection_metric_value","rmse","evaluation_result","winner","null_threshold"}):b.append("POST_EVALUATION_FIELD_PRESENT_IN_PREREGISTRATION")
    return b
def audit_model_selection_prereg(policy:Mapping[str,Any],preregistration:Mapping[str,Any]|None):
    b=[]
    if policy.get("schema")!="CFB_MODEL_SELECTION_POLICY_V1":b.append("POLICY_SCHEMA_MISMATCH")
    if policy.get("status")!="FROZEN_BEFORE_CANDIDATE_EVALUATION":b.append("POLICY_NOT_FROZEN_BEFORE_EVALUATION")
    try: budget,attempts=int(policy.get("candidate_attempt_budget")),int(policy.get("attempts_consumed"))
    except (TypeError,ValueError): budget,attempts=-1,-1;b.append("ATTEMPT_ACCOUNTING_INVALID")
    families=policy.get("candidate_families_predeclared")
    if not isinstance(families,list) or not families or not all(_nonempty_string(x) for x in families):families=[];b.append("PREDECLARED_FAMILIES_INVALID")
    if budget!=len(families):b.append("ATTEMPT_BUDGET_FAMILY_COUNT_MISMATCH")
    if attempts<0 or attempts>budget:b.append("ATTEMPTS_CONSUMED_OUT_OF_RANGE")
    specs=None if preregistration is None else preregistration.get("candidates")
    if not isinstance(specs,Mapping):b.append("CANDIDATE_PREREGISTRATION_MISSING");specs={}
    if set(map(str,specs))-set(map(str,families)):b.append("UNDECLARED_CANDIDATE_FAMILY_PRESENT")
    rows=[]
    for family in families:
        c=specs.get(family); rb=["CANDIDATE_SPEC_MISSING"] if not isinstance(c,Mapping) else _candidate_blockers(c,family)
        if family not in IMPLEMENTED_FAMILIES and "EXECUTABLE_FAMILY_IMPLEMENTATION_MISSING" not in rb:rb.append("EXECUTABLE_FAMILY_IMPLEMENTATION_MISSING")
        if rb:b.append(f"CANDIDATE_INCOMPLETE:{family}")
        rows.append({"family":family,"complete":not rb,"executable":family in IMPLEMENTED_FAMILIES,"blockers":rb})
    ready=not b and attempts==0
    if attempts!=0:b.append("FIRST_EVALUATION_GATE_REQUIRES_ZERO_ATTEMPTS_CONSUMED");ready=False
    return {"schema":"CFB_MODEL_SELECTION_PREREG_AUDIT_V1","status":"READY_FOR_FIRST_EVALUATION" if ready else "BLOCKED_PREREG_INCOMPLETE","candidate_attempt_budget":budget,"attempts_consumed":attempts,"implemented_families":sorted(IMPLEMENTED_FAMILIES),"candidate_results":rows,"blockers":b,"attempt_consumed_by_this_audit":False,"model_fit_performed":False,"model_p_created":False,"promotion_authority":False,"eligibility_changed":False}
__all__=["audit_model_selection_prereg","REQUIRED_SPEC_FIELDS"]
