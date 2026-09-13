#!/usr/bin/env python3
"""Materialize promotion-grade NFL inputs from the frozen source contract.

There is deliberately no source fallback. Transport retries repeat the exact
contract URI only. Bytes move into the evidence source tree only after their
SHA-256 matches the contract, so a failed download or changed asset cannot
reach model fitting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sportsedge.sports.nfl.source_contract import (
    expand_nfl_source_contract,
    load_nfl_source_contract,
    source_contract_sha256,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target(root: Path, name: str, uri: str) -> Path:
    if name == "schedule":
        return root / "games.csv"
    if name == "stadiums":
        return root / "team_stadiums.csv"
    if name == "starter_overrides":
        return root / "nfl_historical_starter_overrides.json"
    if name.startswith("pbp_"):
        return root / "pbp" / Path(uri).name
    if name.startswith("participation_"):
        return root / "participation" / Path(uri).name
    if name.startswith("depth_"):
        return root / "depth" / Path(uri).name
    raise ValueError(f"NFL_SOURCE_MATERIALIZE_TARGET_UNSUPPORTED:{name}")


def _download_exact(uri: str, target: Path, *, retries: int, retry_delay: float) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".partial")
    tmp.unlink(missing_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(uri, headers={"User-Agent": "SportsEdge-source-freeze/1"})
            with urlopen(request, timeout=60) as response, tmp.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            tmp.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(retry_delay)
    raise RuntimeError(f"NFL_SOURCE_TRANSPORT_FAILED:{uri}:{retries}:{last_error}")


def materialize(
    *,
    contract_path: Path,
    output_root: Path,
    attestation_out: Path,
    retries: int = 5,
    retry_delay: float = 2.0,
) -> dict:
    contract = load_nfl_source_contract(contract_path)
    expanded = expand_nfl_source_contract(contract)
    rows: list[dict[str, str]] = []

    for name in sorted(expanded):
        row = expanded[name]
        uri = row["uri"]
        expected = row["expected_sha256"]
        target = _target(output_root, name, uri)
        _download_exact(uri, target, retries=retries, retry_delay=retry_delay)
        tmp = target.with_name(target.name + ".partial")
        observed = _sha256(tmp)
        if observed != expected:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"NFL_SOURCE_CONTRACT_SHA256_MISMATCH:{name}:"
                f"expected={expected}:observed={observed}"
            )
        os.replace(tmp, target)
        rows.append({
            "name": name,
            "uri": uri,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "materialized_path": target.as_posix(),
        })

    payload = {
        "schema_version": 1,
        "sport": "nfl",
        "contract": contract["contract"],
        "source_contract_sha256": source_contract_sha256(contract),
        "status": "PASS",
        "source_count": len(rows),
        "verified_before_model_fit": True,
        "no_fallback": True,
        "sources": rows,
    }
    attestation_out.parent.mkdir(parents=True, exist_ok=True)
    attestation_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attestation-out", type=Path, required=True)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.retries < 1:
        raise SystemExit("NFL_SOURCE_MATERIALIZE_RETRIES_INVALID")
    if args.retry_delay < 0:
        raise SystemExit("NFL_SOURCE_MATERIALIZE_RETRY_DELAY_INVALID")
    payload = materialize(
        contract_path=args.source_contract,
        output_root=args.output_root,
        attestation_out=args.attestation_out,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    print(json.dumps({
        "status": payload["status"],
        "source_count": payload["source_count"],
        "source_contract_sha256": payload["source_contract_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
