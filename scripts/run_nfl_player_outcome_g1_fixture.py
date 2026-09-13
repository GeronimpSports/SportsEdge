"""Deterministic fixture readout for NFL player outcome engine G1."""
from __future__ import annotations

import json
from pathlib import Path
import sys

# When this file is executed directly (``python scripts/...py``), Python puts the
# scripts directory—not the repository root—at sys.path[0]. Add the repository
# root explicitly so the fixture exercises the checked-out SportsEdge package in
# the same deterministic way on hosted runners and local shells.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sportsedge.sports.nfl.player_outcomes_g1_validation import chronological_receptions_readout


def main() -> int:
    rows = []
    for player_id, values in {
        "p1": [3, 4, 5, 6, 4, 7, 5, 8],
        "p2": [1, 2, 1, 3, 2, 2, 4, 3],
    }.items():
        for week, receptions in enumerate(values, start=1):
            rows.append({"player_id": player_id, "season": 2025, "week": week, "receptions": receptions})
    out = chronological_receptions_readout(rows, line=4.5, min_prior_games=5)
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
