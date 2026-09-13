import pytest
from sportsedge.sports.nfl.v2l_candidate_identity import build_candidate_identity, bind_distribution

H="a"*64

def rng():
    return {"bit_generator":"PCG64","seed_sequence":"FIXED","seed":20260913,"simulation_count":50000,"numpy_version":"2.5.3"}

def test_readout_policy_changes_identity():
    a=build_candidate_identity(prereg_sha256=H,code_sha256=H,source_manifest_sha256=H,feature_policy_sha256=H,eval_policy_sha256=H,benchmark_policy_sha256=H,first_readout_policy_sha256=H,fold_definition_sha256=H,environment_lock_sha256=H,rng_policy=rng())
    b=build_candidate_identity(prereg_sha256=H,code_sha256=H,source_manifest_sha256=H,feature_policy_sha256=H,eval_policy_sha256=H,benchmark_policy_sha256=H,first_readout_policy_sha256="b"*64,fold_definition_sha256=H,environment_lock_sha256=H,rng_policy=rng())
    assert a["candidate_identity_sha256"] != b["candidate_identity_sha256"]
    assert a["model_p_authority"] is False

def test_distribution_binds_candidate_and_readout_policy():
    d={"distribution_sha256":"c"*64}
    out=bind_distribution(d,candidate_identity_sha256="d"*64,fit_sha256="e"*64,first_readout_policy_sha256="f"*64)
    assert out["schema"]=="SPORTSEDGE_NFL_V2L_BOUND_DISTRIBUTION_V1"
    assert out["first_readout_policy_sha256"]=="f"*64
    assert out["official_authority"] is False

def test_incomplete_rng_blocks():
    with pytest.raises(ValueError):
        build_candidate_identity(prereg_sha256=H,code_sha256=H,source_manifest_sha256=H,feature_policy_sha256=H,eval_policy_sha256=H,benchmark_policy_sha256=H,first_readout_policy_sha256=H,fold_definition_sha256=H,environment_lock_sha256=H,rng_policy={})
