import pytest
from sportsedge.sports.nfl.v2l_benchmark import build_m1_benchmark, fold_joint_score_rmse

H="a"*64
M="b"*64

def cap(**kw):
    x={"game_id":"g1","captured_at_utc":"2025-09-01T12:00:00+00:00","kickoff_utc":"2025-09-01T17:00:00+00:00","home_ml":-120,"away_ml":110,"home_spread":-2.5,"game_total":44.5,"capture_sha256":"c"*64}
    x.update(kw); return x

def test_deterministic_and_bound():
    a=build_m1_benchmark(captures=[cap()],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)
    b=build_m1_benchmark(captures=[cap()],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)
    assert a["benchmark_evidence_sha256"]==b["benchmark_evidence_sha256"]
    assert a["benchmark_source_manifest_sha256"]==M
    assert a["model_p_authority"] is False

def test_capture_after_kickoff_blocks():
    with pytest.raises(ValueError):
        build_m1_benchmark(captures=[cap(captured_at_utc="2025-09-01T18:00:00+00:00")],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)

def test_equivalent_offset_is_compared_by_instant():
    with pytest.raises(ValueError):
        build_m1_benchmark(captures=[cap(captured_at_utc="2025-09-01T13:00:00-04:00",kickoff_utc="2025-09-01T17:00:00Z")],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)

def test_naive_timestamp_blocks():
    with pytest.raises(ValueError):
        build_m1_benchmark(captures=[cap(captured_at_utc="2025-09-01T12:00:00")],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)

def test_invalid_american_odds_blocks():
    with pytest.raises(ValueError):
        build_m1_benchmark(captures=[cap(home_ml=-95)],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)

def test_missing_capture_blocks_fold():
    e=build_m1_benchmark(captures=[cap()],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)
    with pytest.raises(ValueError): fold_joint_score_rmse(evidence=e,game_ids=["g2"],actual_scores={"g2":[20,17]})

def test_fold_rmse_comes_from_bound_rows():
    e=build_m1_benchmark(captures=[cap()],benchmark_policy_sha256=H,benchmark_source_manifest_sha256=M)
    r=fold_joint_score_rmse(evidence=e,game_ids=["g1"],actual_scores={"g1":[24,20]})
    assert r>=0
