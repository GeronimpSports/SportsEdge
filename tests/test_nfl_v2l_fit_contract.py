import pytest
from sportsedge.sports.nfl.v2l_fit_contract import DriveRow, fit_pit, params_for_matchup

SRC='a'*64
POL='b'*64
CODE='abcdef1'

def rows():
    out=[]
    for g in range(20):
        for i in range(14): out.append(DriveRow(f'g{g}', '2025-01-01T00:00:00Z', 'A', 'B', 25.0, 'TD' if i%3==0 else 'PUNT_OTHER'))
        for i in range(10): out.append(DriveRow(f'h{g}', '2025-01-01T00:00:00Z', 'C', 'D', 25.0, 'FG' if i%8==0 else 'PUNT_OTHER'))
    return out

def test_matchups_resolve_distinct_parameters():
    fit=fit_pit(rows(),prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
    ab=params_for_matchup(fit,offense='A',defense='B',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    cd=params_for_matchup(fit,offense='C',defense='D',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    assert ab.outcome_probs != cd.outcome_probs
    assert ab.drives_mean != cd.drives_mean

def test_opponent_swap_changes_matchup():
    fit=fit_pit(rows(),prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
    ab=params_for_matchup(fit,offense='A',defense='B',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    ad=params_for_matchup(fit,offense='A',defense='D',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    assert ab.drives_mean != ad.drives_mean or ab.outcome_probs != ad.outcome_probs

def test_unseen_team_falls_back_to_league_mean():
    fit=fit_pit(rows(),prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
    x=params_for_matchup(fit,offense='UNKNOWN',defense='UNKNOWN',expected_source_manifest_sha256=SRC,expected_feature_policy_sha256=POL,expected_code_sha=CODE)
    assert abs(sum(x.outcome_probs.values())-1.0)<1e-12
    assert abs(x.drives_mean-fit['base_params']['drives_mean'])<1e-12

def test_future_row_blocks():
    bad=[DriveRow('g','2026-01-01T00:00:00Z','A','B',25.0,'TD')]
    with pytest.raises(ValueError,match='PIT violation'):
        fit_pit(bad,prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)

def test_missing_defense_blocks():
    bad=[DriveRow('g','2025-01-01T00:00:00Z','A','',25.0,'TD')]
    with pytest.raises(ValueError,match='defense identity'):
        fit_pit(bad,prediction_cutoff_utc='2026-01-01T00:00:00Z',source_manifest_sha256=SRC,feature_policy_sha256=POL,code_sha=CODE)
