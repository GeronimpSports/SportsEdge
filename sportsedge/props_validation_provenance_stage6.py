"""Hash-bound Stage 6 validation provenance for research prop engines.

This module wraps the existing metric gate with evidence identity.  It does not
create Model_P or production authority.  Predictions, PIT records, and realized
outcomes remain separate inputs until this layer binds them deterministically.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping, Sequence

from sportsedge.props_pit_stage5 import validate_pit_inputs
from sportsedge.props_validation_stage6 import validate_probability_rows

SCHEMA_VERSION="PROP_VALIDATION_ATTESTATION_V1"
AUTHORITY="RESEARCH_ONLY"


def _dt(value:object,name:str)->datetime:
    try:
        out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError) as exc:
        raise ValueError(f"BOUND_VALIDATION_TIMESTAMP_INVALID:{name}") from exc
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError(f"BOUND_VALIDATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE:{name}")
    return out


def _identity(value:object,name:str)->str:
    out=str(value or "").strip()
    if not out:raise ValueError(f"BOUND_VALIDATION_IDENTITY_REQUIRED:{name}")
    return out


def _hex(value:object,length:int,name:str)->str:
    out=str(value or "").strip().lower()
    if len(out)!=length or any(ch not in "0123456789abcdef" for ch in out):
        raise ValueError(f"BOUND_VALIDATION_HASH_INVALID:{name}")
    return out


def _canonical_bytes(value:object)->bytes:
    try:
        return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc:
        raise ValueError("BOUND_VALIDATION_CANONICALIZATION_INVALID") from exc


def _canonical_sha256(value:object)->str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _metric_number(value:float)->float|None:
    return float(value) if isfinite(float(value)) else None


def validation_attestation_sha256(attestation:Mapping[str,Any])->str:
    payload=dict(attestation)
    payload.pop("artifact_sha256",None)
    return _canonical_sha256(payload)


def verify_validation_attestation(attestation:Mapping[str,Any])->dict[str,Any]:
    if not isinstance(attestation,Mapping):raise ValueError("VALIDATION_ATTESTATION_INVALID")
    payload=dict(attestation)
    if payload.get("schema_version")!=SCHEMA_VERSION:raise ValueError("VALIDATION_ATTESTATION_SCHEMA_INVALID")
    if payload.get("authority")!=AUTHORITY:raise ValueError("VALIDATION_ATTESTATION_AUTHORITY_INVALID")
    expected=_hex(payload.get("artifact_sha256"),64,"artifact_sha256")
    actual=validation_attestation_sha256(payload)
    if actual!=expected:raise ValueError("VALIDATION_ATTESTATION_HASH_MISMATCH")
    if payload.get("passed") is not isinstance(payload.get("passed"),bool):
        raise ValueError("VALIDATION_ATTESTATION_PASS_FLAG_INVALID")
    if payload.get("status") != ("PASS" if payload["passed"] else "FAIL"):
        raise ValueError("VALIDATION_ATTESTATION_STATUS_CONTRADICTION")
    return payload


def build_bound_validation_attestation(
    predictions:Sequence[Mapping[str,Any]],
    outcomes:Sequence[Mapping[str,Any]],
    *,
    pit_records:Mapping[str,Mapping[str,Any]],
    sport:str,
    model_id:str,
    model_version:str,
    code_git_sha:str,
    min_n:int=200,
    ece_max:float=.025,
    max_bin_deviation_max:float=.05,
    slope_min:float=.90,
    slope_max:float=1.10,
    intercept_abs_max:float=.03,
)->dict[str,Any]:
    """Bind chronological prediction evidence to PIT, folds, model identity, and outcomes.

    `predictions` are immutable pre-event records. `outcomes` are supplied
    separately so realized results cannot mutate the prediction record. Each PIT
    record is revalidated by Stage 5 and its canonical hash must match the
    prediction's declared PIT binding.
    """
    resolved_sport=_identity(sport,"sport").upper()
    if resolved_sport not in {"NFL","CFB","MLB"}:raise ValueError("BOUND_VALIDATION_SPORT_UNSUPPORTED")
    resolved_model_id=_identity(model_id,"model_id")
    resolved_model_version=_identity(model_version,"model_version")
    resolved_code_sha=_hex(code_git_sha,40,"code_git_sha")
    xs=list(predictions); ys=list(outcomes)
    if not xs:raise ValueError("NO_BOUND_VALIDATION_PREDICTIONS")
    if not isinstance(pit_records,Mapping):raise ValueError("BOUND_VALIDATION_PIT_RECORDS_INVALID")

    outcome_by_id:dict[str,Mapping[str,Any]]={}
    for raw in ys:
        if not isinstance(raw,Mapping):raise ValueError("BOUND_VALIDATION_OUTCOME_INVALID")
        prediction_id=_identity(raw.get("prediction_id"),"outcome_prediction_id")
        if prediction_id in outcome_by_id:raise ValueError(f"BOUND_VALIDATION_OUTCOME_DUPLICATE:{prediction_id}")
        outcome_by_id[prediction_id]=raw

    seen_prediction_ids:set[str]=set()
    seen_units:set[tuple[str,str,str]]=set()
    seen_fold_order:list[str]=[]
    closed_folds:set[str]=set()
    active_fold:str|None=None
    fold_contracts:dict[str,dict[str,str]]={}
    metric_rows:list[dict[str,Any]]=[]
    row_bindings:list[dict[str,Any]]=[]

    for raw in xs:
        if not isinstance(raw,Mapping):raise ValueError("BOUND_VALIDATION_PREDICTION_INVALID")
        prediction_id=_identity(raw.get("prediction_id"),"prediction_id")
        if prediction_id in seen_prediction_ids:raise ValueError(f"BOUND_VALIDATION_PREDICTION_DUPLICATE:{prediction_id}")
        seen_prediction_ids.add(prediction_id)
        event_id=_identity(raw.get("event_id"),"event_id")
        entity_id=_identity(raw.get("entity_id"),"entity_id")
        market_id=_identity(raw.get("market_id"),"market_id")
        unit=(event_id,entity_id,market_id)
        if unit in seen_units:raise ValueError(f"BOUND_VALIDATION_UNIT_DUPLICATE:{event_id}:{entity_id}:{market_id}")
        seen_units.add(unit)

        fold_id=_identity(raw.get("fold_id"),"fold_id")
        if active_fold is None:
            active_fold=fold_id;seen_fold_order.append(fold_id)
        elif fold_id!=active_fold:
            closed_folds.add(active_fold)
            if fold_id in closed_folds:raise ValueError(f"BOUND_VALIDATION_FOLD_REENTRY:{fold_id}")
            active_fold=fold_id;seen_fold_order.append(fold_id)

        model_artifact_sha=_hex(raw.get("model_artifact_sha256"),64,"model_artifact_sha256")
        declared_pit_sha=_hex(raw.get("pit_record_sha256"),64,"pit_record_sha256")
        prediction_asof=_dt(raw.get("prediction_asof_ts"),"prediction_asof_ts")
        event_start=_dt(raw.get("event_start_ts"),"event_start_ts")
        train_cutoff=_dt(raw.get("train_cutoff_ts"),"train_cutoff_ts")
        calibration_cutoff=_dt(raw.get("calibration_fit_cutoff_ts"),"calibration_fit_cutoff_ts")
        if not calibration_cutoff<=train_cutoff<prediction_asof<event_start:
            raise ValueError(f"BOUND_VALIDATION_TEMPORAL_LEAKAGE:{prediction_id}")

        fold_contract={
            "train_cutoff_ts":str(raw.get("train_cutoff_ts")),
            "calibration_fit_cutoff_ts":str(raw.get("calibration_fit_cutoff_ts")),
            "model_artifact_sha256":model_artifact_sha,
        }
        prior_fold=fold_contracts.get(fold_id)
        if prior_fold is not None and prior_fold!=fold_contract:
            raise ValueError(f"BOUND_VALIDATION_FOLD_IDENTITY_DRIFT:{fold_id}")
        fold_contracts.setdefault(fold_id,fold_contract)

        pit_raw=pit_records.get(prediction_id)
        if not isinstance(pit_raw,Mapping):raise ValueError(f"BOUND_VALIDATION_PIT_RECORD_MISSING:{prediction_id}")
        pit=validate_pit_inputs(resolved_sport,pit_raw)
        if pit["pit_record_sha256"]!=declared_pit_sha:raise ValueError(f"BOUND_VALIDATION_PIT_HASH_MISMATCH:{prediction_id}")
        if str(pit.get("entity_id"))!=entity_id:raise ValueError(f"BOUND_VALIDATION_PIT_ENTITY_MISMATCH:{prediction_id}")
        if _dt(pit.get("asof_ts"),"pit_asof_ts")!=prediction_asof:raise ValueError(f"BOUND_VALIDATION_PIT_ASOF_MISMATCH:{prediction_id}")
        if _dt(pit.get("event_start_ts"),"pit_event_start_ts")!=event_start:raise ValueError(f"BOUND_VALIDATION_PIT_EVENT_MISMATCH:{prediction_id}")

        outcome=outcome_by_id.get(prediction_id)
        if outcome is None:raise ValueError(f"BOUND_VALIDATION_OUTCOME_MISSING:{prediction_id}")
        outcome_observed=_dt(outcome.get("outcome_observed_at_ts"),"outcome_observed_at_ts")
        if outcome_observed<event_start:raise ValueError(f"BOUND_VALIDATION_OUTCOME_OBSERVED_BEFORE_EVENT:{prediction_id}")
        try:
            y=float(outcome["outcome"])
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError(f"BOUND_VALIDATION_OUTCOME_BAD:{prediction_id}") from exc
        if not isfinite(y) or y not in {0.0,1.0}:raise ValueError(f"BOUND_VALIDATION_OUTCOME_BAD:{prediction_id}")

        row={"event_start_ts":str(raw.get("event_start_ts")),"model_probability":raw.get("model_probability"),"outcome":y}
        prediction_has_quantity="quantity_prediction" in raw
        outcome_has_quantity="quantity_actual" in outcome
        if prediction_has_quantity!=outcome_has_quantity:raise ValueError(f"BOUND_VALIDATION_QUANTITY_BINDING_INCOMPLETE:{prediction_id}")
        if prediction_has_quantity:
            row["quantity_prediction"]=raw.get("quantity_prediction")
            row["quantity_actual"]=outcome.get("quantity_actual")
        metric_rows.append(row)
        row_binding={
            "prediction_id":prediction_id,
            "event_id":event_id,
            "entity_id":entity_id,
            "market_id":market_id,
            "fold_id":fold_id,
            "prediction_asof_ts":str(raw.get("prediction_asof_ts")),
            "event_start_ts":str(raw.get("event_start_ts")),
            "train_cutoff_ts":str(raw.get("train_cutoff_ts")),
            "calibration_fit_cutoff_ts":str(raw.get("calibration_fit_cutoff_ts")),
            "pit_record_sha256":declared_pit_sha,
            "model_artifact_sha256":model_artifact_sha,
            "model_probability":raw.get("model_probability"),
            "outcome":y,
            "outcome_observed_at_ts":str(outcome.get("outcome_observed_at_ts")),
        }
        if prediction_has_quantity:
            row_binding["quantity_prediction"]=raw.get("quantity_prediction")
            row_binding["quantity_actual"]=outcome.get("quantity_actual")
        row_bindings.append(row_binding)

    extras=set(outcome_by_id)-seen_prediction_ids
    if extras:raise ValueError("BOUND_VALIDATION_ORPHAN_OUTCOMES:"+",".join(sorted(extras)))

    # Fold training cutoffs may only move forward as held-out chronology advances.
    cutoff_sequence=[_dt(fold_contracts[fold]["train_cutoff_ts"],"fold_train_cutoff_ts") for fold in seen_fold_order]
    if cutoff_sequence!=sorted(cutoff_sequence):raise ValueError("BOUND_VALIDATION_FOLD_CUTOFF_REVERSED")

    thresholds={
        "min_n":int(min_n),"ece_max":float(ece_max),"max_bin_deviation_max":float(max_bin_deviation_max),
        "slope_min":float(slope_min),"slope_max":float(slope_max),"intercept_abs_max":float(intercept_abs_max),
    }
    result=validate_probability_rows(metric_rows,**thresholds)
    metrics={
        "n":result.n,"brier":result.brier,"log_loss":result.log_loss,
        "mae":_metric_number(result.mae),"rmse":_metric_number(result.rmse),
        "ece":result.ece,"max_bin_deviation":result.max_bin_deviation,
        "calibration_slope":result.calibration_slope,"calibration_intercept":result.calibration_intercept,
        "chronological":result.chronological,
    }
    attestation={
        "schema_version":SCHEMA_VERSION,
        "authority":AUTHORITY,
        "status":"PASS" if result.passed else "FAIL",
        "passed":bool(result.passed),
        "sport":resolved_sport,
        "model_id":resolved_model_id,
        "model_version":resolved_model_version,
        "code_git_sha":resolved_code_sha,
        "prediction_count":len(row_bindings),
        "fold_order":seen_fold_order,
        "fold_contracts":fold_contracts,
        "thresholds":thresholds,
        "metrics":metrics,
        "rows":row_bindings,
        "separate_outcome_binding":True,
        "pit_hash_binding":True,
        "market_prices_used_as_model_inputs":False,
        "can_create_model_p":False,
        "can_promote":False,
        "staking_authority":False,
        "official_authority":False,
    }
    attestation["artifact_sha256"]=validation_attestation_sha256(attestation)
    return attestation
