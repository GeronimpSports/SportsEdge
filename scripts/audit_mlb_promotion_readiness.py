#!/usr/bin/env python3
"""Print floor-aware MLB promotion readiness without changing authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sportsedge.mlb_promotion_readiness import build_mlb_promotion_readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edge-floor-config", default="config/truth_gate_floors.json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = build_mlb_promotion_readiness(edge_floor_path=args.edge_floor_config)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
