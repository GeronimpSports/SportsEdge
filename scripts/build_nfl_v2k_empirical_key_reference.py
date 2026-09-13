#!/usr/bin/env python3
"""Build the frozen NFL V2K signed-key empirical reference from bound evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path

FIRST_SEASON = 2018
LAST_SEASON = 2025
SEASON_TYPE = "REG"
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


def _require_sha(path: Path, expected: str, label: str) -> tuple[bytes, str]:
    raw = path.read_bytes()
    actual = sha256_bytes(raw)
    if actual != expected:
        raise SystemExit(f"{label}_SHA256_MISMATCH:{actual}")
    return raw, actual


def _verify_manifest(raw: bytes) -> dict:
    manifest = json.loads(raw)
    if manifest.get("manifest_sha256") != EXPECTED_MANIFEST_DECLARED_SHA256:
        raise SystemExit("SOURCE_MANIFEST_DECLARED_SHA256_MISMATCH")
    if manifest.get("schedule_anchor_sha256") != EXPECTED_GAMES_SHA256:
        raise SystemExit("SOURCE_MANIFEST_SCHEDULE_ANCHOR_MISMATCH")
    schedule_entries = [s for s in manifest.get("sources", []) if s.get("name") == "schedule"]
    if len(schedule_entries) != 1 or schedule_entries[0].get("sha256") != EXPECTED_GAMES_SHA256:
        raise SystemExit("SOURCE_MANIFEST_SCHEDULE_ENTRY_MISMATCH")
    return manifest


def _reference_from_games(raw: bytes) -> tuple[int, dict[str, int], dict[str, dict[str, float | int]]]:
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    margins: list[int] = []
    per_season = Counter()
    for row in rows:
        try:
            season = int(row.get("season") or "")
        except ValueError:
            continue
        if row.get("game_type") != SEASON_TYPE or not (FIRST_SEASON <= season <= LAST_SEASON):
            continue
        home_score = str(row.get("home_score") or "").strip()
        away_score = str(row.get("away_score") or "").strip()
        if not home_score or not away_score:
            raise SystemExit(f"MISSING_FINAL_SCORE:{row.get('game_id')}")
        margin = int(home_score) - int(away_score)
        margins.append(margin)
        per_season[str(season)] += 1
    n = len(margins)
    if n == 0:
        raise SystemExit("EMPTY_REFERENCE_WINDOW")
    counts = Counter(margins)
    by_key: dict[str, dict[str, float | int]] = {}
    for key in SIGNED_KEYS:
        count = counts[key]
        p = count / n
        se = math.sqrt(p * (1.0 - p) / n)
        low, high = wilson95(count, n)
        by_key[str(key)] = {
            "count": count,
            "probability": p,
            "standard_error": se,
            "ci95_low": low,
            "ci95_high": high,
        }
    return n, dict(sorted(per_season.items())), by_key


def _control_metrics(production_raw: bytes, registry_raw: bytes, reference: dict[str, dict[str, float | int]]) -> dict:
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
        sum((float(probs[str(k)]) - float(reference[str(k)]["probability"])) ** 2 for k in SIGNED_KEYS)
        / len(SIGNED_KEYS)
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
    policy = template.get("reference_policy") or {}
    if (policy.get("season_type"), policy.get("first_season"), policy.get("last_season")) != (
        SEASON_TYPE,
        FIRST_SEASON,
        LAST_SEASON,
    ):
        raise SystemExit("REFERENCE_POLICY_WINDOW_MISMATCH")
    if template.get("required_signed_keys") != list(SIGNED_KEYS):
        raise SystemExit("REFERENCE_POLICY_SIGNED_KEYS_MISMATCH")
    if float(template.get("absolute_mass_tolerance")) != 0.005:
        raise SystemExit("REFERENCE_POLICY_TOLERANCE_MISMATCH")

    games_raw, games_sha = _require_sha(games_path, EXPECTED_GAMES_SHA256, "GAMES")
    manifest_raw, manifest_file_sha = _require_sha(manifest_path, EXPECTED_MANIFEST_FILE_SHA256, "SOURCE_MANIFEST_FILE")
    _verify_manifest(manifest_raw)
    production_raw, production_sha = _require_sha(production_path, EXPECTED_PRODUCTION_VALIDATION_SHA256, "PRODUCTION_VALIDATION")
    registry_raw, registry_sha = _require_sha(registry_path, EXPECTED_PROMOTION_REGISTRY_SHA256, "PROMOTION_REGISTRY")

    n, per_season, signed_mass = _reference_from_games(games_raw)
    control = _control_metrics(production_raw, registry_raw, signed_mass)
    builder_sha = sha256_bytes(Path(__file__).read_bytes())

    out = json.loads(json.dumps(template))
    out["status"] = "FROZEN_READY"
    out["reference"] = {
        "season_scope": {
            "season_type": SEASON_TYPE,
            "first_season": FIRST_SEASON,
            "last_season": LAST_SEASON,
        },
        "game_count": n,
        "per_season_game_count": per_season,
        "raw_source_sha256": games_sha,
        "builder_code_sha256": builder_sha,
        "source_manifest_sha256": EXPECTED_MANIFEST_DECLARED_SHA256,
        "source_manifest_file_sha256": manifest_file_sha,
        "evidence_workflow_run_id": EVIDENCE_WORKFLOW_RUN_ID,
        "evidence_artifact_id": EVIDENCE_ARTIFACT_ID,
        "evidence_artifact_digest": EVIDENCE_ARTIFACT_DIGEST,
        "signed_margin_mass": signed_mass,
        "control_metrics": control,
    }
    out["block_reason"] = None
    out["build_attestation"] = {
        "games_sha256_verified": games_sha == EXPECTED_GAMES_SHA256,
        "manifest_file_sha256_verified": manifest_file_sha == EXPECTED_MANIFEST_FILE_SHA256,
        "manifest_schedule_anchor_verified": True,
        "production_validation_sha256_verified": production_sha == EXPECTED_PRODUCTION_VALIDATION_SHA256,
        "promotion_registry_sha256_verified": registry_sha == EXPECTED_PROMOTION_REGISTRY_SHA256,
        "hand_entered_reference_values_used": False,
        "sportsbook_prices_used": False,
        "v2k_simulations_used": False,
    }
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
        "game_count": out["reference"]["game_count"],
        "builder_code_sha256": out["reference"]["builder_code_sha256"],
        "control_signed_key_mass_rmse": out["reference"]["control_metrics"]["signed_key_mass_rmse"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
