"""Canonical multi-source provenance manifest for NFL production evidence."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .source_contract import bind_observed_sources_to_contract


NFL_SOURCE_MANIFEST_V2_CONTRACT = "NFL_MULTI_SOURCE_MANIFEST_V2_FROZEN_SOURCE_IDENTITY"


def _sha256(value: Any, error: str) -> str:
    raw = str(value or "").strip().lower()
    if len(raw) != 64:
        raise ValueError(error)
    try:
        int(raw, 16)
    except ValueError as exc:
        raise ValueError(error) from exc
    return raw


def build_nfl_source_manifest(
    sources: Iterable[Mapping[str, Any]],
    *,
    schedule_anchor_sha256: str,
    source_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical NFL source manifest.

    Without ``source_contract`` this intentionally preserves the original V1
    payload byte-for-byte for legacy evidence consumers. Promotion-grade callers
    may explicitly opt into V2, which first verifies the observed source set and
    hashes against the frozen upstream contract and then records those identities
    in the evidence manifest.
    """
    anchor = _sha256(schedule_anchor_sha256, "NFL_SOURCE_SCHEDULE_ANCHOR_INVALID")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in sources:
        name = str(raw.get("name") or "").strip()
        uri = str(raw.get("uri") or "").strip()
        if not name:
            raise ValueError("NFL_SOURCE_NAME_REQUIRED")
        if name in seen:
            raise ValueError(f"NFL_SOURCE_NAME_DUPLICATE:{name}")
        if not uri:
            raise ValueError(f"NFL_SOURCE_URI_REQUIRED:{name}")
        seen.add(name)
        normalized.append({
            "name": name,
            "uri": uri,
            "sha256": _sha256(raw.get("sha256"), f"NFL_SOURCE_SHA256_INVALID:{name}"),
        })
    if not normalized:
        raise ValueError("NFL_SOURCE_MANIFEST_EMPTY")
    schedule = next((row for row in normalized if row["name"] == "schedule"), None)
    if schedule is None:
        raise ValueError("NFL_SOURCE_SCHEDULE_ENTRY_REQUIRED")
    if schedule["sha256"] != anchor:
        raise ValueError("NFL_SOURCE_SCHEDULE_ANCHOR_MISMATCH")
    normalized.sort(key=lambda row: (row["name"], row["uri"], row["sha256"]))

    if source_contract is None:
        return {
            "schema_version": 1,
            "sport": "nfl",
            "schedule_anchor_sha256": anchor,
            "sources": normalized,
        }

    attestation = bind_observed_sources_to_contract(normalized, source_contract)
    bound_sources = list(attestation["sources"])
    bound_schedule = next((row for row in bound_sources if row["name"] == "schedule"), None)
    if bound_schedule is None:
        raise ValueError("NFL_SOURCE_SCHEDULE_ENTRY_REQUIRED")
    if bound_schedule["observed_sha256"] != anchor:
        raise ValueError("NFL_SOURCE_SCHEDULE_ANCHOR_MISMATCH")
    return {
        "schema_version": 2,
        "sport": "nfl",
        "contract": NFL_SOURCE_MANIFEST_V2_CONTRACT,
        "schedule_anchor_sha256": anchor,
        "source_contract": attestation["contract"],
        "source_contract_sha256": attestation["source_contract_sha256"],
        "source_count": attestation["source_count"],
        "sources": bound_sources,
    }


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(manifest), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
