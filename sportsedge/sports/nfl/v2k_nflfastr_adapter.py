"""Fail-closed nflfastR -> V2K drive-row adapter. Research only."""
from __future__ import annotations
from typing import Iterable, Mapping
from .v2k_fit_contract import DriveRow

# Deliberately explicit. Unknown/ambiguous raw labels block rather than being
# silently folded into PUNT_OTHER.
_RESULT_MAP={
 "Touchdown":"TD", "Field goal":"FG", "Field Goal":"FG",
 "Punt":"PUNT_OTHER", "End of half":"PUNT_OTHER", "End of game":"PUNT_OTHER",
 "Interception":"TURNOVER", "Fumble":"TURNOVER", "Turnover on downs":"TURNOVER",
 "Safety":"SAFETY",
}

def classify_drive_result(raw_result: str, *, defensive_or_special_teams_td: bool=False) -> str:
    if defensive_or_special_teams_td: return "DEF_ST_TD"
    key=str(raw_result or "").strip()
    if key not in _RESULT_MAP: raise ValueError(f"unmapped nflfastR drive result: {key!r}")
    return _RESULT_MAP[key]

def adapt_drive_rows(rows: Iterable[Mapping]) -> list[DriveRow]:
    out=[]; seen=set()
    for r in rows:
        game=str(r.get("game_id") or "").strip()
        offense=str(r.get("posteam") or r.get("offense") or "").strip()
        defense=str(r.get("defteam") or r.get("defense") or "").strip()
        kickoff=str(r.get("kickoff_utc") or "").strip()
        drive_id=str(r.get("drive") or r.get("drive_id") or "").strip()
        if not all((game,offense,defense,kickoff,drive_id)):
            raise ValueError("raw drive missing game/offense/defense/kickoff/drive identity")
        if offense==defense: raise ValueError("offense and defense must differ")
        identity=(game,drive_id)
        if identity in seen: raise ValueError("duplicate raw drive identity")
        seen.add(identity)
        # start_yard is a required upstream-normalized coordinate: yards from
        # the offense's own goal line, 1..99, increasing toward the opponent end zone.
        # Raw provider yard-line fields are intentionally not guessed here.
        yard=r.get("start_yard")
        if yard is None: raise ValueError("raw drive missing normalized start_yard")
        yard=float(yard)
        if not 1.0 <= yard <= 99.0: raise ValueError("normalized start_yard outside 1..99")
        result=r.get("drive_result") if r.get("drive_result") is not None else r.get("result")
        outcome=classify_drive_result(str(result or ""), defensive_or_special_teams_td=bool(r.get("def_st_td",False)))
        out.append(DriveRow(game,drive_id,kickoff,offense,defense,yard,outcome))
    if not out: raise ValueError("no drive rows adapted")
    return out
