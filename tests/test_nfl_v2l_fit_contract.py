import pytest
from sportsedge.sports.nfl.v2l_fit_contract import DriveRow, fit_pit, params_for_matchup

SRC='a'*64
POL='b'*64
CODE='abcdef1'

def rows():
    out=[]
    for i in range(240):
        out.append(DriveRow(f'g{i//12}', '2025-01-01T00:00:00Z', 'A', 'B', 25.0, 'TD' if i%3==0 else 'PUNT_OTHER'))
        out.append(DriveRow(f'h{i//12}', '2025-01-01T00:00:00Z', 'C', 'D', 25.0, 'FG' if i%8==0 else 'PUNT_OTHER'))
    return out

def test_matchups_resolve_distinct_parameters():
    fit=fit_pit(rows(),prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
    ab=params_for_matchup(fit,offense='A',defense='B',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    cd=params_for_matchup(fit,offense='C',defense='D',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    assert ab.outcome_probs != cd.outcome_probs

def test_unseen_team_falls_back_to_league_mean():
    fit=fit_pit(rows(),prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
    x=params_for_matchup(fit,offense='UNKNOWN',defense='UNKNOWN',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    assert abs(sum(x.outcome_probs.values())-1.0)<1e-12

def test_future_row_blocks():
    bad=[DriveRow('g','2026-01-01T00:00:00Z','A','B',25.0,'TD')]
    with pytest.raises(ValueError,match='PIT violation'):
        fit_pit(bad,prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)

def test_missing_defense_blocks():
    bad=[DriveRow('g','2025-01-01T00:00:00Z','A','',25.0,'TD')]
    with pytest.raises(ValueError,match='defense identity'):
        fit_pit(bad,prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
