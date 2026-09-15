from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .schema import PlayRecord


def build_game_analytics(plays: list[PlayRecord]) -> dict[str, Any]:
    by_offense: dict[str, list[PlayRecord]] = defaultdict(list)
    for play in plays:
        if play.offense:
            by_offense[play.offense].append(play)

    teams: dict[str, Any] = {}
    for team, team_plays in sorted(by_offense.items()):
        success_known = [p.success for p in team_plays if p.success is not None]
        epa_known = [p.epa for p in team_plays if p.epa is not None]
        yards_known = [p.yards_gained for p in team_plays if p.yards_gained is not None]
        teams[team] = {
            "plays_indexed": len(team_plays),
            "yards_on_indexed_plays": sum(yards_known) if yards_known else None,
            "success_rate": (sum(bool(x) for x in success_known) / len(success_known)) if success_known else None,
            "epa_per_play": mean(epa_known) if epa_known else None,
            "explosive_plays": sum(1 for p in team_plays if p.explosive is True),
            "explosive_rate": (
                sum(1 for p in team_plays if p.explosive is True)
                / sum(1 for p in team_plays if p.explosive is not None)
            )
            if any(p.explosive is not None for p in team_plays)
            else None,
        }

    return {
        "teams": teams,
        "plays_indexed": len(plays),
        "coverage_note": "Metrics cover only the plays present in the ingested source payload.",
    }
