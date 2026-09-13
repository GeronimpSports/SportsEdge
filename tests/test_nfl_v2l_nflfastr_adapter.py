import pytest
from sportsedge.sports.nfl.v2l_nflfastr_adapter import adapt_drive_rows, normalize_team

def raw(**kw):
    x={"game_id":"g1","kickoff_utc":"2019-09-01T17:00:00Z","drive":"1","posteam":"OAK","defteam":"DEN","start_yard":25,"drive_result":"Punt"}
    x.update(kw); return x

def test_offense_defense_and_relocation_alias_are_deterministic():
    row=adapt_drive_rows([raw()])[0]
    assert row.offense=="LV" and row.defense=="DEN"
    assert normalize_team("JAC")=="JAX"

def test_missing_defteam_blocks():
    with pytest.raises(ValueError,match="unmapped NFL team identity"):
        adapt_drive_rows([raw(defteam=None)])

def test_unknown_alias_blocks():
    with pytest.raises(ValueError,match="unmapped NFL team identity"):
        adapt_drive_rows([raw(defteam="XYZ")])

def test_same_team_blocks():
    with pytest.raises(ValueError,match="must differ"):
        adapt_drive_rows([raw(posteam="DEN",defteam="DEN")])

def test_duplicate_drive_blocks():
    with pytest.raises(ValueError,match="duplicate"):
        adapt_drive_rows([raw(),raw()])
