#!/usr/bin/env python3
"""Run production NFL validation only after frozen source identity verification.

This wrapper intentionally leaves the canonical production fitting implementation
unchanged. It verifies all source bytes against a checked-in contract *before*
invoking that runner, then upgrades only the provenance binding from the legacy
V1 observed-byte manifest to the frozen-identity V2 manifest before downstream
evidence consumes the generated bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sportsedge.sports.nfl.source_contract import (
    bind_observed_sources_to_contract,
    load_nfl_source_contract,
)
from sportsedge.sports.nfl.source_manifest import build_nfl_source_manifest, manifest_sha256

_WRAPPER_OPTIONS = {"--source-contract", "--freeze-attestation-out"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one_file(directory: Path, stem: str, season: int) -> Path:
    candidates = [
        directory / f"{stem}_{season}.csv.gz",
        directory / f"{stem}_{season}.csv",
    ]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) != 1:
        raise ValueError(f"NFL_FROZEN_SOURCE_FILE_COUNT:{season}:{stem}:{len(existing)}")
    return existing[0]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--schedule-file", type=Path, required=True)
    parser.add_argument("--pbp-dir", type=Path, required=True)
    parser.add_argument("--participation-dir", type=Path, required=True)
    parser.add_argument("--depth-dir", type=Path, required=True)
    parser.add_argument("--stadium-file", type=Path, required=True)
    parser.add_argument(
        "--starter-override-file",
        type=Path,
        default=Path("config/nfl_historical_starter_overrides.json"),
    )
    parser.add_argument("--start-season", type=int, default=2016)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--out", type=Path, default=Path("artifacts/football/nfl_production_validation.json"))
    parser.add_argument("--manifest-out", type=Path, default=Path("artifacts/football/nfl_source_manifest.json"))
    parser.add_argument("--model-out", type=Path, default=Path("artifacts/football/nfl_m2_model.json"))
    parser.add_argument("--qb-coverage-out", type=Path, default=Path("artifacts/football/nfl_starting_qb_coverage.json"))
    parser.add_argument("--source-contract", type=Path, required=True)
    parser.add_argument(
        "--freeze-attestation-out",
        type=Path,
        default=Path("artifacts/football/nfl_source_freeze_attestation.json"),
    )
    return parser


def _child_argv(argv: list[str]) -> list[str]:
    out: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in _WRAPPER_OPTIONS:
            if index + 1 >= len(argv):
                raise ValueError(f"NFL_SOURCE_FREEZE_WRAPPER_OPTION_VALUE_MISSING:{token}")
            index += 2
            continue
        if any(token.startswith(option + "=") for option in _WRAPPER_OPTIONS):
            index += 1
            continue
        out.append(token)
        index += 1
    return out


def _observed_sources(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.end_season < args.start_season:
        raise ValueError("END_SEASON_BEFORE_START_SEASON")
    paths: list[tuple[str, Path]] = [
        ("schedule", args.schedule_file),
        ("stadiums", args.stadium_file),
        ("starter_overrides", args.starter_override_file),
    ]
    for season in range(args.start_season, args.end_season + 1):
        paths.extend([
            (f"pbp_{season}", _one_file(args.pbp_dir, "play_by_play", season)),
            (
                f"participation_{season}",
                _one_file(args.participation_dir, "pbp_participation", season),
            ),
            (f"depth_{season}", _one_file(args.depth_dir, "depth_charts", season)),
        ])
    observed: list[dict[str, str]] = []
    for name, path in paths:
        if not path.is_file():
            raise ValueError(f"NFL_SOURCE_FREEZE_FILE_MISSING:{name}:{path}")
        observed.append({"name": name, "uri": f"observed-file://{path.as_posix()}", "sha256": _sha(path)})
    return observed


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _replace_manifest_identity(value: Any, *, old_hash: str, new_hash: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_manifest_identity(item, old_hash=old_hash, new_hash=new_hash)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_manifest_identity(item, old_hash=old_hash, new_hash=new_hash)
            for item in value
        ]
    if isinstance(value, str):
        if value == old_hash:
            return new_hash
        if value == f"manifest://sha256/{old_hash}":
            return f"manifest://sha256/{new_hash}"
    return value


def _contains_manifest_identity(value: Any, manifest_hash: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_manifest_identity(item, manifest_hash) for item in value.values())
    if isinstance(value, list):
        return any(_contains_manifest_identity(item, manifest_hash) for item in value)
    return isinstance(value, str) and manifest_hash in value


def _legacy_manifest_base(payload: dict[str, Any]) -> dict[str, Any]:
    base = dict(payload)
    base.pop("manifest_sha256", None)
    # The canonical runner appends this attribution after calculating the
    # manifest hash, so it is deliberately outside the legacy identity unit.
    base.pop("participation_attribution", None)
    return base


def upgrade_generated_bundle(
    *,
    args: argparse.Namespace,
    source_contract: dict[str, Any],
    observed_sources: list[dict[str, str]],
) -> str:
    try:
        legacy_manifest = json.loads(args.manifest_out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_MANIFEST_UNREADABLE") from exc
    if not isinstance(legacy_manifest, dict) or legacy_manifest.get("schema_version") != 1:
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_MANIFEST_SCHEMA_INVALID")
    old_hash = str(legacy_manifest.get("manifest_sha256") or "").strip().lower()
    if len(old_hash) != 64 or any(ch not in "0123456789abcdef" for ch in old_hash):
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_MANIFEST_HASH_INVALID")
    if manifest_sha256(_legacy_manifest_base(legacy_manifest)) != old_hash:
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_MANIFEST_HASH_MISMATCH")
    legacy_sources = legacy_manifest.get("sources")
    if not isinstance(legacy_sources, list):
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_MANIFEST_SOURCES_INVALID")
    # Prove the canonical runner itself saw the same allowed source set/bytes
    # before replacing its generic legacy URIs with frozen upstream identities.
    bind_observed_sources_to_contract(legacy_sources, source_contract)

    schedule = next((row for row in observed_sources if row["name"] == "schedule"), None)
    if schedule is None:
        raise ValueError("NFL_SOURCE_FREEZE_SCHEDULE_SOURCE_MISSING")
    if legacy_manifest.get("schedule_anchor_sha256") != schedule["sha256"]:
        raise ValueError("NFL_SOURCE_FREEZE_LEGACY_SCHEDULE_ANCHOR_MISMATCH")

    v2_manifest = build_nfl_source_manifest(
        observed_sources,
        schedule_anchor_sha256=schedule["sha256"],
        source_contract=source_contract,
    )
    new_hash = manifest_sha256(v2_manifest)
    v2_payload = dict(v2_manifest)
    v2_payload["manifest_sha256"] = new_hash
    participation = legacy_manifest.get("participation_attribution")
    if participation is not None:
        v2_payload["participation_attribution"] = participation
    _write_json(args.manifest_out, v2_payload)

    for path in (args.out, args.model_out, args.qb_coverage_out):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"NFL_SOURCE_FREEZE_GENERATED_ARTIFACT_UNREADABLE:{path}") from exc
        if not _contains_manifest_identity(payload, old_hash):
            raise ValueError(f"NFL_SOURCE_FREEZE_GENERATED_ARTIFACT_SOURCE_BINDING_MISSING:{path}")
        upgraded = _replace_manifest_identity(payload, old_hash=old_hash, new_hash=new_hash)
        if _contains_manifest_identity(upgraded, old_hash):
            raise ValueError(f"NFL_SOURCE_FREEZE_STALE_MANIFEST_IDENTITY:{path}")
        if not _contains_manifest_identity(upgraded, new_hash):
            raise ValueError(f"NFL_SOURCE_FREEZE_NEW_MANIFEST_IDENTITY_MISSING:{path}")
        _write_json(path, upgraded)
    return new_hash


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args, _unknown = _parser().parse_known_args(raw_argv)
    contract = load_nfl_source_contract(args.source_contract)
    observed = _observed_sources(args)
    attestation = bind_observed_sources_to_contract(observed, contract)
    attestation = {
        **attestation,
        "phase": "PRE_MODEL_FIT",
        "verified_before_model_fit": True,
    }
    # Persist pre-fit PASS before invoking the canonical runner. If that child
    # fails, no post-fit/bundle-upgrade PASS marker is ever written.
    _write_json(args.freeze_attestation_out, attestation)

    child = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "run_nfl_production_validation.py"),
        *_child_argv(raw_argv),
    ]
    completed = subprocess.run(child, cwd=_REPO_ROOT, check=False)
    if completed.returncode != 0:
        return int(completed.returncode)

    new_manifest_hash = upgrade_generated_bundle(
        args=args,
        source_contract=contract,
        observed_sources=observed,
    )
    attestation["v2_source_manifest_sha256"] = new_manifest_hash
    attestation["bundle_upgrade_status"] = "PASS"
    _write_json(args.freeze_attestation_out, attestation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
