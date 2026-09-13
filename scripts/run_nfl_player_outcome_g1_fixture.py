"""Deterministic fixture readout for NFL player outcome engine G1."""
from __future__ import annotations

import json

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
