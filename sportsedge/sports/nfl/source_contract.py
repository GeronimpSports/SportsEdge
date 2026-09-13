"""Frozen upstream identity contract for promotion-grade NFL historical evidence.

The existing source manifest proves which bytes a single run consumed.  This
contract additionally proves which bytes the run was *allowed* to consume, so a
later rerun at the same SportsEdge code SHA cannot silently accept changed
upstream release assets or a moving schedule branch.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

SOURCE_CONTRACT_SCHEMA_VERSION = 1
SOURCE_CONTRACT_ID = "NFL_PROMOTION_SOURCE_FREEZE_V1"
STATIC_SOURCE_NAMES = ("schedule", "stadiums", "starter_overrides")
SEASONAL_SOURCE_NAMES = ("pbp", "participation", "depth")


def _sha256(value: Any, error: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise ValueError(error)
    return raw


def _identity(value: Any, error: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(error)
    return raw


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("NFL_SOURCE_CONTRACT_CANONICALIZATION_INVALID") from exc


def source_contract_sha256(contract: Mapping[str, Any]) -> str:
    if not isinstance(contract, Mapping):
        raise ValueError("NFL_SOURCE_CONTRACT_INVALID")
    return hashlib.sha256(_canonical_json_bytes(dict(contract))).hexdigest()


def load_nfl_source_contract(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("NFL_SOURCE_CONTRACT_UNREADABLE") from exc
    if not isinstance(payload, dict):
        raise ValueError("NFL_SOURCE_CONTRACT_INVALID")
    # Expansion is the schema validator; do it here so callers cannot load an
    # apparently valid but structurally unusable contract.
    expand_nfl_source_contract(payload)
    return payload


def _upstream_identity(raw: Any, *, name: str, season: int | None = None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"NFL_SOURCE_CONTRACT_UPSTREAM_IDENTITY_INVALID:{name}")
    identity = dict(raw)
    identity_type = _identity(
        identity.get("type"), f"NFL_SOURCE_CONTRACT_UPSTREAM_IDENTITY_TYPE_REQUIRED:{name}"
    )
    if identity_type in {"git_commit_blob", "git_commit_path"}:
        repository = _identity(
            identity.get("repository"), f"NFL_SOURCE_CONTRACT_REPOSITORY_REQUIRED:{name}"
        )
        commit_sha = str(identity.get("commit_sha") or "").strip().lower()
        if len(commit_sha) != 40 or any(ch not in "0123456789abcdef" for ch in commit_sha):
            raise ValueError(f"NFL_SOURCE_CONTRACT_COMMIT_SHA_INVALID:{name}")
        path = _identity(identity.get("path"), f"NFL_SOURCE_CONTRACT_PATH_REQUIRED:{name}")
        normalized: dict[str, Any] = {
            "type": identity_type,
            "repository": repository,
            "commit_sha": commit_sha,
            "path": path,
        }
        if identity_type == "git_commit_blob":
            blob = str(identity.get("git_blob_sha1") or "").strip().lower()
            if len(blob) != 40 or any(ch not in "0123456789abcdef" for ch in blob):
                raise ValueError(f"NFL_SOURCE_CONTRACT_GIT_BLOB_SHA1_INVALID:{name}")
            normalized["git_blob_sha1"] = blob
        return normalized
    if identity_type == "sportsedge_repo_file":
        return {
            "type": identity_type,
            "path": _identity(identity.get("path"), f"NFL_SOURCE_CONTRACT_PATH_REQUIRED:{name}"),
        }
    if identity_type == "github_release_asset":
        if season is None:
            raise ValueError(f"NFL_SOURCE_CONTRACT_RELEASE_SEASON_REQUIRED:{name}")
        repository = _identity(
            identity.get("repository"), f"NFL_SOURCE_CONTRACT_REPOSITORY_REQUIRED:{name}"
        )
        release_tag = _identity(
            identity.get("release_tag"), f"NFL_SOURCE_CONTRACT_RELEASE_TAG_REQUIRED:{name}"
        )
        asset_template = _identity(
            identity.get("asset_template"), f"NFL_SOURCE_CONTRACT_ASSET_TEMPLATE_REQUIRED:{name}"
        )
        try:
            asset_name = asset_template.format(season=season)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"NFL_SOURCE_CONTRACT_ASSET_TEMPLATE_INVALID:{name}") from exc
        if "{" in asset_name or "}" in asset_name:
            raise ValueError(f"NFL_SOURCE_CONTRACT_ASSET_TEMPLATE_INVALID:{name}")
        immutable = identity.get("provider_release_immutable")
        if not isinstance(immutable, bool):
            raise ValueError(f"NFL_SOURCE_CONTRACT_RELEASE_IMMUTABLE_FLAG_INVALID:{name}")
        return {
            "type": identity_type,
            "repository": repository,
            "release_tag": release_tag,
            "asset_name": asset_name,
            "provider_release_immutable": immutable,
        }
    raise ValueError(f"NFL_SOURCE_CONTRACT_UPSTREAM_IDENTITY_TYPE_UNSUPPORTED:{name}:{identity_type}")


def expand_nfl_source_contract(contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(contract, Mapping):
        raise ValueError("NFL_SOURCE_CONTRACT_INVALID")
    if contract.get("schema_version") != SOURCE_CONTRACT_SCHEMA_VERSION:
        raise ValueError("NFL_SOURCE_CONTRACT_SCHEMA_INVALID")
    if str(contract.get("sport") or "").strip().lower() != "nfl":
        raise ValueError("NFL_SOURCE_CONTRACT_SPORT_INVALID")
    if contract.get("contract") != SOURCE_CONTRACT_ID:
        raise ValueError("NFL_SOURCE_CONTRACT_ID_INVALID")

    frozen_from = contract.get("frozen_from_evidence")
    if not isinstance(frozen_from, Mapping):
        raise ValueError("NFL_SOURCE_CONTRACT_EVIDENCE_ANCHOR_INVALID")
    code_sha = str(frozen_from.get("sportsedge_code_git_sha") or "").strip().lower()
    if len(code_sha) != 40 or any(ch not in "0123456789abcdef" for ch in code_sha):
        raise ValueError("NFL_SOURCE_CONTRACT_EVIDENCE_CODE_SHA_INVALID")
    _sha256(
        frozen_from.get("source_manifest_sha256"),
        "NFL_SOURCE_CONTRACT_EVIDENCE_MANIFEST_SHA256_INVALID",
    )

    static = contract.get("sources")
    if not isinstance(static, Mapping) or set(static) != set(STATIC_SOURCE_NAMES):
        raise ValueError("NFL_SOURCE_CONTRACT_STATIC_SOURCE_SET_INVALID")
    seasonal = contract.get("seasonal_sources")
    if not isinstance(seasonal, Mapping) or set(seasonal) != set(SEASONAL_SOURCE_NAMES):
        raise ValueError("NFL_SOURCE_CONTRACT_SEASONAL_SOURCE_SET_INVALID")

    expanded: dict[str, dict[str, Any]] = {}
    for name in STATIC_SOURCE_NAMES:
        raw = static[name]
        if not isinstance(raw, Mapping):
            raise ValueError(f"NFL_SOURCE_CONTRACT_SOURCE_INVALID:{name}")
        uri = _identity(raw.get("uri"), f"NFL_SOURCE_CONTRACT_URI_REQUIRED:{name}")
        expected = _sha256(
            raw.get("expected_sha256"), f"NFL_SOURCE_CONTRACT_SHA256_INVALID:{name}"
        )
        expanded[name] = {
            "name": name,
            "uri": uri,
            "expected_sha256": expected,
            "upstream_identity": _upstream_identity(raw.get("upstream_identity"), name=name),
        }

    for prefix in SEASONAL_SOURCE_NAMES:
        raw = seasonal[prefix]
        if not isinstance(raw, Mapping):
            raise ValueError(f"NFL_SOURCE_CONTRACT_SOURCE_INVALID:{prefix}")
        seasons_raw = raw.get("seasons")
        if not isinstance(seasons_raw, list) or not seasons_raw:
            raise ValueError(f"NFL_SOURCE_CONTRACT_SEASONS_INVALID:{prefix}")
        seasons: list[int] = []
        for season in seasons_raw:
            if isinstance(season, bool) or not isinstance(season, int) or season < 1900 or season > 2200:
                raise ValueError(f"NFL_SOURCE_CONTRACT_SEASON_INVALID:{prefix}")
            seasons.append(season)
        if len(set(seasons)) != len(seasons) or seasons != sorted(seasons):
            raise ValueError(f"NFL_SOURCE_CONTRACT_SEASONS_NOT_UNIQUE_SORTED:{prefix}")
        uri_template = _identity(
            raw.get("uri_template"), f"NFL_SOURCE_CONTRACT_URI_TEMPLATE_REQUIRED:{prefix}"
        )
        expected_by_season = raw.get("expected_sha256_by_season")
        if not isinstance(expected_by_season, Mapping):
            raise ValueError(f"NFL_SOURCE_CONTRACT_HASH_MAP_INVALID:{prefix}")
        if set(expected_by_season) != {str(season) for season in seasons}:
            raise ValueError(f"NFL_SOURCE_CONTRACT_HASH_SEASON_SET_INVALID:{prefix}")
        for season in seasons:
            name = f"{prefix}_{season}"
            try:
                uri = uri_template.format(season=season)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"NFL_SOURCE_CONTRACT_URI_TEMPLATE_INVALID:{prefix}") from exc
            if "{" in uri or "}" in uri:
                raise ValueError(f"NFL_SOURCE_CONTRACT_URI_TEMPLATE_INVALID:{prefix}")
            expected = _sha256(
                expected_by_season[str(season)], f"NFL_SOURCE_CONTRACT_SHA256_INVALID:{name}"
            )
            if name in expanded:
                raise ValueError(f"NFL_SOURCE_CONTRACT_NAME_DUPLICATE:{name}")
            expanded[name] = {
                "name": name,
                "uri": uri,
                "expected_sha256": expected,
                "upstream_identity": _upstream_identity(
                    raw.get("upstream_identity"), name=name, season=season
                ),
            }
    return expanded


def bind_observed_sources_to_contract(
    observed_sources: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    expected = expand_nfl_source_contract(contract)
    observed: dict[str, dict[str, str]] = {}
    for raw in observed_sources:
        if not isinstance(raw, Mapping):
            raise ValueError("NFL_SOURCE_CONTRACT_OBSERVED_SOURCE_INVALID")
        name = _identity(raw.get("name"), "NFL_SOURCE_CONTRACT_OBSERVED_NAME_REQUIRED")
        if name in observed:
            raise ValueError(f"NFL_SOURCE_CONTRACT_OBSERVED_NAME_DUPLICATE:{name}")
        observed[name] = {
            "name": name,
            "observed_sha256": _sha256(
                raw.get("sha256"), f"NFL_SOURCE_CONTRACT_OBSERVED_SHA256_INVALID:{name}"
            ),
        }

    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing:
        raise ValueError("NFL_SOURCE_CONTRACT_REQUIRED_SOURCE_MISSING:" + ",".join(missing))
    if extra:
        raise ValueError("NFL_SOURCE_CONTRACT_UNEXPECTED_SOURCE:" + ",".join(extra))

    bound_sources: list[dict[str, Any]] = []
    for name in sorted(expected):
        expected_row = expected[name]
        observed_hash = observed[name]["observed_sha256"]
        expected_hash = expected_row["expected_sha256"]
        if observed_hash != expected_hash:
            raise ValueError(
                f"NFL_SOURCE_CONTRACT_SHA256_MISMATCH:{name}:"
                f"expected={expected_hash}:observed={observed_hash}"
            )
        bound_sources.append({
            "name": name,
            "uri": expected_row["uri"],
            "expected_sha256": expected_hash,
            "observed_sha256": observed_hash,
            "sha256": observed_hash,
            "upstream_identity": expected_row["upstream_identity"],
        })

    return {
        "schema_version": 1,
        "sport": "nfl",
        "contract": SOURCE_CONTRACT_ID,
        "source_contract_sha256": source_contract_sha256(contract),
        "status": "PASS",
        "source_count": len(bound_sources),
        "sources": bound_sources,
    }
