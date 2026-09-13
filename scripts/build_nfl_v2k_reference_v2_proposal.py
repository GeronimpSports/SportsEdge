#!/usr/bin/env python3
"""Build report-only NFL V2K empirical signed-key reference policy evidence.

This builder intentionally cannot admit implementation or grant model/pricing/staking
or OFFICIAL authority. It produces reproducible evidence for human review of a
versioned reference-policy proposal while leaving frozen V1 governance untouched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path

SIGNED_KEYS = (-7, -3, 3, 7)
EXPECTED_GAMES_SHA256 = "902f1a3796d576ee846e2b54e99b46a5ab1bdd17bd34c93e8f9f1f797f61281e"
EXPECTED_MANIFEST_DECLARED_SHA256 = "5d6d5ec66012039100d0954622d45ced6ed79c48dba355e3cf2ec2c3ec59342a"
EXPECTED_MANIFEST_FILE_SHA256 = "ea8915e5b63ed7c0b4450b948f54bff3547e1b203650b59a2c68004425e8908d"
EXPECTED_PRODUCTION_VALIDATION_SHA256 = "7a18bf664e9a701b251c62430ec80d7da410d068f95e9d0110a46f3248b94ada"
EXPECTED_PROMOTION_REGISTRY_SHA256 = "821af436a066db4d3a7382ecd3280e8cb562e7668f7a5a0677be4fe74dff72dc"
EVIDENCE_ARTIFACT_DIGEST = "sha256:e53f16804c74ec197b23dd17180ad88d1c696d4a93e593ecc17fa8ccf480a437"
EVIDENCE_WORKFLOW_RUN_ID = 34763311001
EVIDENCE_ARTIFACT_ID = 10319922606
CONTROL_MODEL_ID = "nfl_m2_ridge_v1"

POLICIES = {
    "MODERN_REG_2018_2025": {
        "first_season": 2018,
        "last_season": 2025,
        "season_types": ["REG"],
        "rationale": (
            "Prioritize the post-2018 kickoff-rule era through the last complete pre-2026 season; "
            "accept higher sampling noise in exchange for less scoring-regime mixing."
        ),
    },
    "BROAD_ALL_2002_2025": {
        "first_season": 2002,
        "last_season": 2025,
        "season_types": ["REG", "WC", "DIV", "CON", "SB"],
        "rationale": (
            "Prioritize sample size across the 32-team era and include postseason finals; "
            "accept greater scoring/rules-regime mixing in exchange for lower sampling noise."
        ),
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256_bytes(raw)


def wilson95(successes: int, n: int) -> tuple[float, float]:
    if n <= 0 or successes < 0 or successes > n:
        raise ValueError("INVALID_BINOMIAL_COUNTS")
    z = 1.959963984540054
    p = successes / n
    denom = 1.0 + (z * z / n)
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt((p * (1.0 - p) / n) + (z * z / (4.0 * n * n))) / denom
    return center - half, center + half


def require_sha(path: Path, expected: str, label: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    actual = sha256_bytes(raw)
    if actual != expected:
        raise SystemExit(f"{label}_SHA256_MISMATCH:{actual}")
    return raw, actual


def verify_manifest(raw: bytes) -> dict:
    manifest = json.loads(raw)
    if manifest.get("manifest_sha256") != EXPECTED_MANIFEST_DECLARED_SHA256:
        raise SystemExit("SOURCE_MANIFEST_DECLARED_SHA256_MISMATCH")
    if manifest.get("schedule_anchor_sha256") != EXPECTED_GAMES_SHA256:
        raise SystemExit("SOURCE_MANIFEST_SCHEDULE_ANCHOR_MISMATCH")
    schedule_entries = [s for s in manifest.get("sources", []) if s.get("name") == "schedule"]
    if len(schedule_entries) != 1 or schedule_entries[0].get("sha256") != EXPECTED_GAMES_SHA256:
        raise SystemExit("SOURCE_MANIFEST_SCHEDULE_ENTRY_MISMATCH")
    return manifest


def load_games(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def reference_profile(rows: list[dict[str, str]], policy: dict) -> dict:
    margins: list[int] = []
    per_season = Counter()
    allowed_types = set(policy["season_types"])
    for row in rows:
        try:
            season = int(row.get("season") or "")
        except ValueError:
            continue
        if not (policy["first_season"] <= season <= policy["last_season"]):
            continue
        if row.get("game_type") not in allowed_types:
            continue
        home_score = str(row.get("home_score") or "").strip()
        away_score = str(row.get("away_score") or "").strip()
        if not home_score or not away_score:
            raise SystemExit(f"MISSING_FINAL_SCORE:{row.get('game_id')}")
        margin = int(float(home_score)) - int(float(away_score))
        margins.append(margin)
        per_season[str(season)] += 1

    n = len(margins)
    if n == 0:
        raise SystemExit("EMPTY_REFERENCE_WINDOW")
    counts = Counter(margins)
    by_key = {}
    for key in SIGNED_KEYS:
        count = counts[key]
        p = count / n
        low, high = wilson95(count, n)
        by_key[str(key)] = {
            "count": count,
            "probability": p,
            "standard_error": math.sqrt(p * (1.0 - p) / n),
            "ci95_low": low,
            "ci95_high": high,
        }
    return {
        "game_count": n,
        "per_season_game_count": dict(sorted(per_season.items())),
        "signed_margin_mass": by_key,
    }


def control_metrics(production_raw: bytes, registry_raw: bytes, signed_margin_mass: dict) -> dict:
    production = json.loads(production_raw)
    registry = json.loads(registry_raw)
    profile = production.get("production_distribution_profile") or {}
    if profile.get("model_id") != CONTROL_MODEL_ID:
        raise SystemExit("CONTROL_MODEL_ID_MISMATCH")
    probs = profile.get("signed_key_probability") or {}
    if set(probs) != {str(k) for k in SIGNED_KEYS}:
        raise SystemExit("CONTROL_SIGNED_KEY_SET_MISMATCH")
    slope_gate = (((registry.get("markets") or {}).get("spread") or {}).get("calibration_truth_gate") or {})
    slope = slope_gate.get("slope")
    if not isinstance(slope, (int, float)) or not math.isfinite(float(slope)):
        raise SystemExit("CONTROL_SLOPE_MISSING_OR_INVALID")
    slope = float(slope)
    rmse = math.sqrt(
        sum(
            (float(probs[str(k)]) - float(signed_margin_mass[str(k)]["probability"])) ** 2
            for k in SIGNED_KEYS
        ) / len(SIGNED_KEYS)
    )
    binding = {
        "artifact_digest": EVIDENCE_ARTIFACT_DIGEST,
        "model_id": CONTROL_MODEL_ID,
        "promotion_registry_sha256": EXPECTED_PROMOTION_REGISTRY_SHA256,
        "production_validation_sha256": EXPECTED_PRODUCTION_VALIDATION_SHA256,
        "signed_key_probability": {str(k): float(probs[str(k)]) for k in SIGNED_KEYS},
        "spread_calibration_slope": slope,
    }
    return {
        "control_identity": "NFL_M2_FROZEN_CONTROL",
        "model_id": CONTROL_MODEL_ID,
        "calibration_gate_contract": slope_gate.get("contract"),
        "calibration_slope": slope,
        "calibration_slope_metric": abs(slope - 1.0),
        "signed_key_probability": binding["signed_key_probability"],
        "signed_key_mass_rmse": rmse,
        "production_validation_sha256": EXPECTED_PRODUCTION_VALIDATION_SHA256,
        "promotion_registry_sha256": EXPECTED_PROMOTION_REGISTRY_SHA256,
        "artifact_digest": EVIDENCE_ARTIFACT_DIGEST,
        "provenance_sha256": canonical_sha256(binding),
    }


def build(template_path: Path, games_path: Path, manifest_path: Path, production_path: Path, registry_path: Path) -> dict:
    template = json.loads(template_path.read_text(encoding="utf-8"))
    if template.get("schema") != "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2_PROPOSAL":
        raise SystemExit("PROPOSAL_SCHEMA_MISMATCH")
    if template.get("selected_policy") is not None or template.get("review_decision") is not None:
        raise SystemExit("AUTOMATION_MAY_NOT_PRESELECT_OR_APPROVE_POLICY")
    if template.get("implementation_admitted") is not False:
        raise SystemExit("PROPOSAL_MUST_NOT_ADMIT_IMPLEMENTATION")

    games_raw, games_sha = require_sha(games_path, EXPECTED_GAMES_SHA256, "GAMES")
    manifest_raw, manifest_file_sha = require_sha(manifest_path, EXPECTED_MANIFEST_FILE_SHA256, "SOURCE_MANIFEST_FILE")
    verify_manifest(manifest_raw)
    production_raw, production_sha = require_sha(production_path, EXPECTED_PRODUCTION_VALIDATION_SHA256, "PRODUCTION_VALIDATION")
    registry_raw, registry_sha = require_sha(registry_path, EXPECTED_PROMOTION_REGISTRY_SHA256, "PROMOTION_REGISTRY")
    rows = load_games(games_raw)

    out = json.loads(json.dumps(template))
    out["status"] = "PROPOSED_HUMAN_REVIEW_REQUIRED"
    out["authority"] = "NONE"
    out["implementation_admitted"] = False
    out["selected_policy"] = None
    out["review_decision"] = None
    out["evidence_profiles"] = {}

    for policy_id, policy in POLICIES.items():
        profile = reference_profile(rows, policy)
        profile["policy"] = {
            "first_season": policy["first_season"],
            "last_season": policy["last_season"],
            "season_types": policy["season_types"],
            "sign_convention": "OFFICIAL_SCHEDULE_HOME_FINAL_MINUS_AWAY_FINAL",
            "neutral_site_handling": "INCLUDE_USING_OFFICIAL_SCHEDULE_HOME_AWAY_DESIGNATION",
            "overtime_handling": "OFFICIAL_FINAL_SCORE_INCLUDING_OVERTIME",
            "rationale": policy["rationale"],
        }
        profile["control_metrics"] = control_metrics(production_raw, registry_raw, profile["signed_margin_mass"])
        out["evidence_profiles"][policy_id] = profile

    out["source_provenance"] = {
        "evidence_workflow_run_id": EVIDENCE_WORKFLOW_RUN_ID,
        "evidence_artifact_id": EVIDENCE_ARTIFACT_ID,
        "evidence_artifact_digest": EVIDENCE_ARTIFACT_DIGEST,
        "games_sha256": games_sha,
        "source_manifest_declared_sha256": EXPECTED_MANIFEST_DECLARED_SHA256,
        "source_manifest_file_sha256": manifest_file_sha,
        "production_validation_sha256": production_sha,
        "promotion_registry_sha256": registry_sha,
        "builder_code_sha256": sha256_bytes(Path(__file__).read_bytes()),
    }
    out["build_attestation"] = {
        "component_hashes_verified": True,
        "manifest_schedule_anchor_verified": True,
        "hand_entered_reference_values_used": False,
        "sportsbook_prices_used": False,
        "v2k_simulations_used": False,
        "frozen_v1_reference_mutated": False,
        "attempt_ledger_mutated": False,
        "automation_selected_policy": False,
        "automation_granted_authority": False,
        "artifact_zip_digest_verified_by_builder": False,
        "artifact_zip_digest_expected": EVIDENCE_ARTIFACT_DIGEST,
    }
    out["block_reason"] = (
        "Report-only evidence. Human review must select and explicitly approve a versioned reference policy before "
        "any frozen reference or implementation-admission state may change."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--games", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--production-validation", required=True)
    parser.add_argument("--promotion-registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = build(
        Path(args.template),
        Path(args.games),
        Path(args.manifest),
        Path(args.production_validation),
        Path(args.promotion_registry),
    )
    Path(args.output).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": out["status"],
        "selected_policy": out["selected_policy"],
        "implementation_admitted": out["implementation_admitted"],
        "profiles": {
            k: {
                "game_count": v["game_count"],
                "signed_key_mass_rmse": v["control_metrics"]["signed_key_mass_rmse"],
            }
            for k, v in out["evidence_profiles"].items()
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
