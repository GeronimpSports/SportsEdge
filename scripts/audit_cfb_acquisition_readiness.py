#!/usr/bin/env python3
"""Audit CFB historical-acquisition readiness without making network calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sportsedge.sports.cfb.acquisition_readiness import audit_cfb_acquisition_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="config/cfb_model_selection_policy_v1.json")
    parser.add_argument("--acquisition", default="config/cfb_historical_acquisition_manifest_v1.json")
    parser.add_argument("--out")
    args = parser.parse_args()

    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    path = Path(args.acquisition)
    acquisition = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    report = audit_cfb_acquisition_readiness(policy, acquisition)
    report["acquisition_manifest_path"] = str(path)
    report["acquisition_manifest_present"] = path.exists()
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "READY_FOR_HISTORICAL_REPLAY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
