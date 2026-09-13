"""Immutable source-manifest builder for NFL V2K research inputs.

Research only. The manifest proves which raw objects were acquired before an
untouched readout; it grants no Model_P, promotion, staking, or OFFICIAL authority.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json
from typing import Iterable, Mapping

SCHEMA = "SPORTSEDGE_NFL_V2K_SOURCE_MANIFEST_V1"


def _utc(value: str) -> str:
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("retrieval timestamp must be timezone-aware")
    return d.astimezone(timezone.utc).isoformat()


def _sha(value: object, label: str) -> str:
    out = str(value or "")
    if len(out) != 64 or any(c not in "0123456789abcdefABCDEF" for c in out):
        raise ValueError(f"{label} must be a 64-character SHA256")
    return out.lower()


def build_source_manifest(
    files: Iterable[Mapping[str, object]],
    *,
    provider: str = "nflverse/nflfastR",
    dataset_version: str,
) -> dict:
    rows = []
    for f in files:
        name = str(f.get("name", "")).strip()
        source_identifier = str(f.get("source_identifier", "")).strip()
        season_scope = f.get("season_scope")
        week_scope = f.get("week_scope")
        if not name or not source_identifier:
            raise ValueError("every raw source needs name and source_identifier")
        if season_scope in (None, "", []):
            raise ValueError("every raw source needs season_scope")
        if week_scope in (None, "", []):
            raise ValueError("every raw source needs week_scope")
        rows.append(
            {
                "name": name,
                "source_identifier": source_identifier,
                "retrieved_at_utc": _utc(str(f.get("retrieved_at_utc", ""))),
                "season_scope": season_scope,
                "week_scope": week_scope,
                "byte_sha256": _sha(f.get("byte_sha256", f.get("sha256")), "byte_sha256"),
                "parser_code_sha256": _sha(f.get("parser_code_sha256"), "parser_code_sha256"),
            }
        )
    if not rows or not str(dataset_version).strip():
        raise ValueError("source files and pinned dataset version required")
    rows = sorted(rows, key=lambda x: (x["name"], x["source_identifier"]))
    payload = {
        "schema": SCHEMA,
        "provider": str(provider),
        "dataset_version": str(dataset_version),
        "files": rows,
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    return payload
