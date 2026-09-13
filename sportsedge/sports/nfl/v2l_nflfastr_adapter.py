"""Fail-closed nflfastR -> V2L drive-row adapter.

Research only. No market inputs and no bettor-facing authority.
"""
from __future__ import annotations
from typing import Iterable, Mapping
from .v2l_fit_contract import DriveRow

_RESULT_MAP={
    "Touchdown":"TD", "Field goal":"FG", "Field Goal":"FG",
    "Punt":"PUNT_OTHER", "End of half":"PUNT_OTHER", "End of game":"PUNT_OTHER",
    "Interception":"TURNOVER", "Fumble":"TURNOVER", "Turnover on downs":"TURNOVER",
    "Safety":"SAFETY",
}

# Provider-era aliases are frozen plumbing, not fitted evidence. Relocated
# franchises are resolved to the current nflverse-style identity so train and
# serve use one deterministic key. Unknown aliases block.
_TEAM_ALIASES={
    "ARI":"ARI","ATL":"ATL","BAL":"BAL","BUF":"BUF","CAR":"CAR","CHI":"CHI",
    "CIN":"CIN","CLE":"CLE","DAL":"DAL","DEN":"DEN","DET":"DET","GB":"GB",
    "HOU":"HOU","IND":"IND","JAX":"JAX","JAC":"JAX","KC":"KC","LA":"LA",
    "LAR":"LA","LAC":"LAC","LV":"LV","OAK":"LV","SD":"LAC","STL":"LA",
    "MIA":"MIA","MIN":"MIN","NE":"NE","NO":"NO","NYG":"NYG","NYJ":"NYJ",
    "PHI":"PHI","PIT":"PIT","SEA":"SEA","SF":"SF","TB":"TB","TEN":"TEN",
    "WAS":"WAS","WSH":"WAS",
}

def normalize_team(value: object) -> str:
    key=str(value or "").strip().upper()
    if key not in _TEAM_ALIASES:
        raise ValueError(f"unmapped NFL team identity: {key!r}")
    return _TEAM_ALIASES[key]

def classify_drive_result(raw_result: str, *, defensive_or_special_teams_td: bool=False) -> str:
    if defensive_or_special_teams_td:
        return "DEF_ST_TD"
    key=str(raw_result or "").strip()
    if key not in _RESULT_MAP:
        raise ValueError(f"unmapped nflfastR drive result: {key!r}")
    return _RESULT_MAP[key]

def adapt_drive_rows(rows: Iterable[Mapping]) -> list[DriveRow]:
    out=[]; seen=set()
    for r in rows:
        game=str(r.get("game_id") or "").strip()
        kickoff=str(r.get("kickoff_utc") or "").strip()
        drive_id=str(r.get("drive") or r.get("drive_id") or "").strip()
        if not all((game,kickoff,drive_id)):
            raise ValueError("raw drive missing game/kickoff/drive identity")
        offense=normalize_team(r.get("posteam") if r.get("posteam") is not None else r.get("offense"))
        defense=normalize_team(r.get("defteam") if r.get("defteam") is not None else r.get("defense"))
        if offense==defense:
            raise ValueError("offense and defense identities must differ")
        identity=(game,drive_id)
        if identity in seen:
            raise ValueError("duplicate raw drive identity")
        seen.add(identity)
        yard=r.get("start_yard")
        if yard is None:
            raise ValueError("raw drive missing normalized start_yard")
        yard=float(yard)
        if not 1.0<=yard<=99.0:
            raise ValueError("normalized start_yard outside 1..99")
        result=r.get("drive_result") if r.get("drive_result") is not None else r.get("result")
        outcome=classify_drive_result(str(result or ""), defensive_or_special_teams_td=bool(r.get("def_st_td",False)))
        out.append(DriveRow(game,kickoff,offense,defense,yard,outcome))
    if not out:
        raise ValueError("no drive rows adapted")
    return out
