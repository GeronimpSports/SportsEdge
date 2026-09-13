#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sportsedge.sports.nfl.m2_v2i_candidate import (
    NFL_M2_V2I_CANDIDATE_MODEL_ID,
    NFL_M2_V2I_DISTRIBUTION_CONTRACT,
)
from sportsedge.sports.nfl.simulator_profile import build_nfl_simulator_profile, validate_profile_fit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_json", type=Path)
    parser.add_argument("candidate_evidence", type=Path)
    parser.add_argument("--max-abs-error", type=float, default=0.005)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if float(args.max_abs_error) != 0.005:
        raise SystemExit("NFL_V2I_FROZEN_KEY_TOLERANCE_REQUIRED")

    audit = json.loads(args.audit_json.read_text(encoding="utf-8"))
    evidence = json.loads(args.candidate_evidence.read_text(encoding="utf-8"))
    if evidence.get("status") != "FIRST_READOUT_DIAGNOSTIC_ONLY":
        raise SystemExit("NFL_V2I_FIRST_READOUT_STATUS_REQUIRED")
    if evidence.get("preregistration_locked") is not True or evidence.get("post_readout_retuning_allowed") is not False:
        raise SystemExit("NFL_V2I_PREREG_LOCK_REQUIRED")
    for field in ("promotion_eligible", "promotion_authority", "model_p_authority", "official_status_granted"):
        if evidence.get(field) is not False:
            raise SystemExit(f"NFL_V2I_AUTHORITY_FORBIDDEN:{field}")
    if evidence.get("model_id") != NFL_M2_V2I_CANDIDATE_MODEL_ID:
        raise SystemExit("NFL_V2I_MODEL_ID_MISMATCH")
    if evidence.get("distribution_contract") != NFL_M2_V2I_DISTRIBUTION_CONTRACT:
        raise SystemExit("NFL_V2I_DISTRIBUTION_CONTRACT_MISMATCH")

    profile_payload = evidence.get("candidate_distribution_profile")
    if not isinstance(profile_payload, dict) or profile_payload.get("contract") != "NFL_M2_V2I_OOS_SIGNED_KEY_PMF_V1":
        raise SystemExit("NFL_V2I_PROFILE_INVALID")
    raw_pmf = profile_payload.get("signed_key_probability")
    if not isinstance(raw_pmf, dict):
        raise SystemExit("NFL_V2I_PMF_REQUIRED")

    profile = build_nfl_simulator_profile(audit, version="nfl-v2i-first-readout-oos-key-emergent-v1")
    key_numbers = tuple(sorted(int(key) for key in profile["validation_target_key_frequency"]))
    try:
        candidate_pmf = {key: float(raw_pmf[str(key)]) for key in key_numbers}
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("NFL_V2I_PMF_INVALID") from exc
    fit = validate_profile_fit(profile, candidate_pmf, max_abs_error=0.005)

    payload = {
        "schema_version": 1,
        "status": "FIRST_READOUT_DIAGNOSTIC_ONLY",
        "preregistration_locked": True,
        "post_readout_retuning_allowed": False,
        "promotion_eligible": False,
        "promotion_authority": False,
        "model_p_authority": False,
        "official_status_granted": False,
        "production_registry_consumes_this_artifact": False,
        "model_id": NFL_M2_V2I_CANDIDATE_MODEL_ID,
        "distribution_contract": NFL_M2_V2I_DISTRIBUTION_CONTRACT,
        "historical_profile_version": profile["version"],
        "key_number_contract": profile["key_number_contract"],
        "max_abs_error": 0.005,
        "fit": fit,
        "heldout_game_count": int(profile_payload.get("heldout_game_count", 0)),
        "test_seasons": list(profile_payload.get("test_seasons") or []),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
