#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sportsedge.sports.nfl.m2_v2j_runtime_shard import (
    build_v2j_candidate_evidence_from_raw_exact,
    merge_v2j_raw_evaluation_shards,
)

_EXPECTED_TEST_SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shard-root", type=Path, required=True)
    p.add_argument("--predecessor-run-id", type=int, required=True)
    p.add_argument("--predecessor-head-sha", required=True)
    p.add_argument("--runtime-benchmark-run-id", type=int, required=True)
    p.add_argument("--runtime-benchmark-head-sha", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--execution-attestation-out", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = sorted(args.shard_root.rglob("nfl_v2j_fold_*.json"))
    if len(paths) != len(_EXPECTED_TEST_SEASONS):
        raise SystemExit(
            f"NFL_V2J_TIMEOUT_SUCCESSOR_FOLD_FILE_COUNT_INVALID:{len(paths)}"
        )
    shards = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    seasons = tuple(sorted(int(item.get("test_season")) for item in shards))
    if seasons != _EXPECTED_TEST_SEASONS:
        raise SystemExit(f"NFL_V2J_TIMEOUT_SUCCESSOR_FOLD_SEASONS_INVALID:{seasons}")

    contexts = {_canonical(item.get("readout_context")) for item in shards}
    if len(contexts) != 1:
        raise SystemExit("NFL_V2J_TIMEOUT_SUCCESSOR_READOUT_CONTEXT_DRIFT")
    context = json.loads(next(iter(contexts)))

    source_manifests = {str(item.get("source_manifest_sha256") or "").lower() for item in shards}
    code_shas = {str(item.get("code_git_sha") or "").lower() for item in shards}
    if len(source_manifests) != 1 or len(code_shas) != 1:
        raise SystemExit("NFL_V2J_TIMEOUT_SUCCESSOR_SHARD_IDENTITY_DRIFT")
    source_manifest_sha256 = next(iter(source_manifests))
    code_git_sha = next(iter(code_shas))

    raw = merge_v2j_raw_evaluation_shards(shards)
    evidence = build_v2j_candidate_evidence_from_raw_exact(
        raw,
        source_manifest_sha256=source_manifest_sha256,
        min_calibration_fit_seasons=2,
        calibration_bins=10,
        calibration_min_bin_n=25,
        calibration_threshold=0.05,
        fold_win_threshold=0.65,
        min_train_seasons=2,
    )
    evidence.update(context)

    forbidden = (
        "promotion_eligible",
        "promotion_authority",
        "model_p_authority",
        "official_status_granted",
        "production_registry_consumes_this_artifact",
    )
    if evidence.get("status") != "FIRST_READOUT_DIAGNOSTIC_ONLY":
        raise SystemExit("NFL_V2J_TIMEOUT_SUCCESSOR_STATUS_INVALID")
    for field in forbidden:
        if evidence.get(field) is not False:
            raise SystemExit(f"NFL_V2J_TIMEOUT_SUCCESSOR_ZERO_AUTHORITY_REQUIRED:{field}")
    if evidence.get("post_readout_retuning_allowed") is not False:
        raise SystemExit("NFL_V2J_TIMEOUT_SUCCESSOR_RETUNING_FORBIDDEN")
    if evidence.get("nfl_props") != "NO_ENGINE":
        raise SystemExit("NFL_V2J_TIMEOUT_SUCCESSOR_PROPS_AUTHORITY_FORBIDDEN")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    final_text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    args.out.write_text(final_text, encoding="utf-8")

    shard_digests = []
    for path, shard in zip(paths, shards):
        shard_digests.append({
            "path": path.name,
            "test_season": int(shard["test_season"]),
            "sha256": _sha256_text(_canonical(shard)),
            "test_row_count": int(shard["test_row_count"]),
        })
    attestation = {
        "schema_version": 1,
        "contract": "NFL_V2J_TIMEOUT_SUCCESSOR_EXECUTION_V1",
        "status": "EXACT_FOLD_SHARDED_EXECUTION_COMPLETE_ZERO_AUTHORITY",
        "predecessor_run_id": int(args.predecessor_run_id),
        "predecessor_head_sha": str(args.predecessor_head_sha).lower(),
        "predecessor_result": "CANCELLED_AT_HOSTED_TIMEOUT_NO_ARTIFACT",
        "runtime_benchmark_run_id": int(args.runtime_benchmark_run_id),
        "runtime_benchmark_head_sha": str(args.runtime_benchmark_head_sha).lower(),
        "execution_code_git_sha": code_git_sha,
        "source_manifest_sha256": source_manifest_sha256,
        "fold_geometry": list(_EXPECTED_TEST_SEASONS),
        "shard_count": len(shards),
        "raw_evaluation_count": len(raw),
        "final_evidence_sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
        "shards": shard_digests,
        "predictive_verdict": None,
        "promotion_authority": False,
        "model_p_authority": False,
        "staking_authority": False,
        "official_authority": False,
    }
    args.execution_attestation_out.parent.mkdir(parents=True, exist_ok=True)
    args.execution_attestation_out.write_text(
        json.dumps(attestation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": evidence["status"],
        "raw_evaluation_count": len(raw),
        "fold_count": evidence["fold_count"],
        "source_manifest_sha256": source_manifest_sha256,
        "final_evidence_sha256": attestation["final_evidence_sha256"],
        "promotion_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
