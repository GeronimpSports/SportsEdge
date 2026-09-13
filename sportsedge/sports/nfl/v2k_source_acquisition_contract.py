"""Fail-closed source acquisition contract for NFL V2K historical research.

This module defines the canonical nflverse/nflfastR release URLs and provenance
metadata needed before the first V2K readout. It performs no network I/O and
grants no Model_P, promotion, staking, or OFFICIAL authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping

SCHEMA = "SPORTSEDGE_NFL_V2K_SOURCE_ACQUISITION_CONTRACT_V1"
DEFAULT_PROVIDER = "nflverse/nflverse-data"
DEFAULT_DATASET_TAG = "pbp"
DEFAULT_FORMAT = "parquet"
DEFAULT_SEASONS = tuple(range(2010, 2026))


@dataclass(frozen=True)
class SourceObject:
    season: int
    source_identifier: str
    season_scope: tuple[int, ...]
    week_scope: str


def canonical_pbp_url(season: int, *, dataset_tag: str = DEFAULT_DATASET_TAG,
                      file_format: str = DEFAULT_FORMAT) -> str:
    season = int(season)
    if season < 1999 or season > 2100:
        raise ValueError("season outside supported nflfastR era")
    if dataset_tag != "pbp":
        raise ValueError("V2K acquisition is frozen to nflverse pbp release tag")
    if file_format != "parquet":
        raise ValueError("V2K acquisition is frozen to parquet")
    return (
        "https://github.com/nflverse/nflverse-data/releases/download/"
        f"{dataset_tag}/play_by_play_{season}.{file_format}"
    )


def provider_attested_sha256(asset: Mapping[str, object], *, season: int) -> str:
    """Extract GitHub's release-asset SHA-256 without pretending null is evidence.

    The asset must be the exact canonical parquet object for the requested season.
    A missing/non-SHA256 digest is an evidence blocker and is never substituted by
    an asset id, ETag, Git blob SHA, filename, size, or download URL.
    """
    expected_name = f"play_by_play_{int(season)}.parquet"
    if str(asset.get("name", "")) != expected_name:
        raise ValueError("release asset name does not match canonical V2K source")
    if str(asset.get("state", "")) != "uploaded":
        raise ValueError("release asset is not in uploaded state")
    digest = str(asset.get("digest") or "")
    prefix = "sha256:"
    if not digest.startswith(prefix):
        raise ValueError("provider-attested SHA256 unavailable")
    sha = digest[len(prefix):].lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("malformed provider-attested SHA256")
    return sha


def build_acquisition_plan(seasons: Iterable[int] = DEFAULT_SEASONS) -> dict:
    unique = sorted({int(s) for s in seasons})
    if not unique:
        raise ValueError("at least one season required")
    objects = [
        SourceObject(
            season=s,
            source_identifier=canonical_pbp_url(s),
            season_scope=(s,),
            week_scope="REG+POST",
        )
        for s in unique
    ]
    return {
        "schema": SCHEMA,
        "provider": DEFAULT_PROVIDER,
        "dataset_tag": DEFAULT_DATASET_TAG,
        "format": DEFAULT_FORMAT,
        "objects": [o.__dict__ for o in objects],
        "accepted_sha256_evidence": [
            "DIRECT_DOWNLOADED_BYTE_SHA256",
            "GITHUB_RELEASE_ASSET_SHA256_DIGEST",
        ],
        "null_provider_digest_requires_direct_byte_hash": True,
        "requires_retrieved_at_utc": True,
        "requires_parser_code_sha256": True,
        "model_p_authority": False,
        "promotion_authority": False,
        "official_authority": False,
    }
