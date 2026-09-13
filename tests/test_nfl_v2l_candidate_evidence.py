import pytest
from sportsedge.sports.nfl.v2l_candidate_evidence import build_candidate_prediction_evidence, joint_score_rmse

H="a"*64

def row(**kw):
    x={"game_id":"g1","season":2020,"home_score_mean":24.0,"away_score_mean":20.0,"bound_distribution_sha256":"b"*64}; x.update(kw); return x

def build(rows=None):
    return build_candidate_prediction_evidence(rows=rows or [row()],candidate_identity_sha256=H,source_manifest_sha256=H,fit_sha256=H,readout_policy_sha256=H)

def test_deterministic_and_metric_derived_from_rows():
    a=build(); b=build(); assert a["candidate_evidence_sha256"]==b["candidate_evidence_sha256"]
    assert joint_score_rmse(evidence=a,game_ids=["g1"],actual_scores={"g1":[24,20]})==0.0

def test_exposed_season_blocks():
    with pytest.raises(ValueError,match="2020"): build([row(season=2021)])

def test_duplicate_game_blocks():
    with pytest.raises(ValueError,match="unique game_id"): build([row(),row()])

def test_missing_fold_lineage_blocks():
    with pytest.raises(ValueError,match="complete candidate fold lineage"): joint_score_rmse(evidence=build(),game_ids=["g2"],actual_scores={"g2":[1,1]})
