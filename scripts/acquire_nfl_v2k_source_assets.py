#!/usr/bin/env python3
"""Acquire unresolved NFL V2K nflverse PBP source bytes and hash them.

Research-source provenance only. This script never imports or invokes a model,
simulator, evaluator, market pricer, promotion gate, or RUN IT surface.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.request import Request, urlopen

from sportsedge.sports.nfl.v2k_source_acquisition_contract import canonical_pbp_url

SCHEMA = "SPORTSEDGE_NFL_V2K_DIRECT_BYTE_ACQUISITION_V1"
DEFAULT_SEASONS = tuple(range(2010, 2019))
USER_AGENT = "SportsEdge-V2K-source-provenance/1.0"
CHUNK_SIZE = 1024 * 1024


def sha256_stream(stream: BinaryIO, *, sink: BinaryIO | None = None) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(CHUNK_SIZE)
        if not chunk:
            break
        h.update(chunk)
        total += len(chunk)
        if sink is not None:
            sink.write(chunk)
    return h.hexdigest(), total


def acquire_one(season: int, *, cache_dir: Path) -> dict:
    url = canonical_pbp_url(season)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"play_by_play_{season}.parquet"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    retrieved_at = datetime.now(timezone.utc).isoformat()
    with urlopen(request, timeout=120) as response, target.open("wb") as sink:
        digest, byte_count = sha256_stream(response, sink=sink)
    if byte_count <= 0:
        raise RuntimeError(f"NFL_V2K_SOURCE_EMPTY:{season}")
    with target.open("rb") as check:
        disk_digest, disk_bytes = sha256_stream(check)
    if disk_digest != digest or disk_bytes != byte_count:
        raise RuntimeError(f"NFL_V2K_SOURCE_WRITE_VERIFY_FAILED:{season}")
    return {
        "season": int(season),
        "source_identifier": url,
        "canonical_filename": target.name,
        "retrieved_at_utc": retrieved_at,
        "sha256": digest,
        "byte_count": byte_count,
        "evidence_method": "DIRECT_DOWNLOADED_BYTE_SHA256",
        "season_scope": [int(season)],
        "week_scope": "REG+POST",
    }


def parse_seasons(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(x.strip()) for x in raw.split(",") if x.strip()}))
    if not values:
        raise ValueError("NFL_V2K_SOURCE_SEASONS_EMPTY")
    for season in values:
        if season < 2010 or season > 2025:
            raise ValueError(f"NFL_V2K_SOURCE_SEASON_OUTSIDE_PREREG:{season}")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", default=",".join(str(x) for x in DEFAULT_SEASONS))
    parser.add_argument("--cache-dir", default="artifacts/football/v2k/source-bytes")
    parser.add_argument("--output", default="artifacts/football/v2k/source-acquisition.json")
    args = parser.parse_args()

    seasons = parse_seasons(args.seasons)
    rows = [acquire_one(season, cache_dir=Path(args.cache_dir)) for season in seasons]
    payload = {
        "schema": SCHEMA,
        "status": "PROVENANCE_ONLY_NOT_MODEL_EVIDENCE",
        "provider": "nflverse/nflverse-data",
        "dataset_tag": "pbp",
        "format": "parquet",
        "requested_seasons": list(seasons),
        "objects": rows,
        "model_fit_invoked": False,
        "evaluation_invoked": False,
        "readout_consumed": False,
        "model_p_authority": False,
        "promotion_authority": False,
        "truth_gate_authority": False,
        "staking_authority": False,
        "official_authority": False,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "seasons": list(seasons), "output": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
