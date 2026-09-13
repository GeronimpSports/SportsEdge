import pytest
from sportsedge.sports.nfl.v2k_nflfastr_adapter import adapt_drive_rows, classify_drive_result

def test_exceptional_scoring_is_explicit():
    assert classify_drive_result("Punt", defensive_or_special_teams_td=True)=="DEF_ST_TD"
    assert classify_drive_result("Safety")=="SAFETY"

def test_unknown_result_fails_closed():
    with pytest.raises(ValueError, match="unmapped"):
        classify_drive_result("Mystery outcome")

def test_duplicate_drive_fails():
    row={"game_id":"g","posteam":"CHI","defteam":"GB","kickoff_utc":"2025-09-01T17:00:00Z","drive":1,"start_yard":25,"drive_result":"Punt"}
    with pytest.raises(ValueError, match="duplicate"):
        adapt_drive_rows([row,row])

def test_adapter_preserves_team_possession_identity():
    rows=[
      {"game_id":"g","posteam":"CHI","defteam":"GB","kickoff_utc":"2025-09-01T17:00:00Z","drive":1,"start_yard":25,"drive_result":"Touchdown"},
      {"game_id":"g","posteam":"GB","defteam":"CHI","kickoff_utc":"2025-09-01T17:00:00Z","drive":2,"start_yard":30,"drive_result":"Field goal"},
    ]
    got=adapt_drive_rows(rows)
    assert [x.drive_id for x in got]==["1","2"]
    assert [x.offense for x in got]==["CHI","GB"]
    assert [x.defense for x in got]==["GB","CHI"]
    assert [x.outcome for x in got]==["TD","FG"]

def test_adapter_rejects_missing_or_same_defense():
    with pytest.raises(ValueError, match="missing"):
        adapt_drive_rows([{"game_id":"g","posteam":"CHI","kickoff_utc":"2025-09-01T17:00:00Z","drive":1,"start_yard":25,"drive_result":"Punt"}])
    with pytest.raises(ValueError, match="must differ"):
        adapt_drive_rows([{"game_id":"g","posteam":"CHI","defteam":"CHI","kickoff_utc":"2025-09-01T17:00:00Z","drive":1,"start_yard":25,"drive_result":"Punt"}])
