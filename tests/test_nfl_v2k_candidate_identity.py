import pytest

from sportsedge.sports.nfl.v2k_candidate_identity import (
    bind_distribution,
    build_candidate_identity,
)

H = {
    "prereg_sha256": "11" * 32,
    "code_sha256": "22" * 32,
    "source_manifest_sha256": "33" * 32,
    "feature_policy_sha256": "44" * 32,
    "eval_policy_sha256": "55" * 32,
    "benchmark_policy_sha256": "66" * 32,
    "fold_definition_sha256": "77" * 32,
    "environment_lock_sha256": "88" * 32,
}
RNG = {
    "bit_generator": "PCG64",
    "seed_sequence": "numpy.random.SeedSequence",
    "seed": 20260913,
    "simulation_count": 50000,
    "numpy_version": "2.5.3",
}


def build(**changes):
    args = dict(H)
    args["rng_policy"] = dict(RNG)
    args.update(changes)
    return build_candidate_identity(**args)


def test_candidate_identity_is_deterministic_and_authority_false():
    a = build()
    b = build()
    assert a == b
    assert len(a["candidate_identity_sha256"]) == 64
    assert a["status"] == "BOUND_BEFORE_FIRST_READOUT"
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False


def test_candidate_identity_changes_when_any_bound_input_changes():
    baseline = build()["candidate_identity_sha256"]
    for key in H:
        changed = dict(H)
        changed[key] = "aa" * 32
        args = dict(changed)
        args["rng_policy"] = dict(RNG)
        assert build_candidate_identity(**args)["candidate_identity_sha256"] != baseline

    rng = dict(RNG)
    rng["seed"] = RNG["seed"] + 1
    assert build(rng_policy=rng)["candidate_identity_sha256"] != baseline


def test_candidate_identity_requires_complete_rng_policy():
    rng = dict(RNG)
    rng.pop("simulation_count")
    with pytest.raises(ValueError, match="complete RNG policy required"):
        build(rng_policy=rng)


def test_candidate_identity_rejects_malformed_sha256():
    with pytest.raises(ValueError, match="prereg_sha256"):
        build(prereg_sha256="deadbeef")


def test_bound_distribution_requires_hashed_distribution():
    identity = build()
    with pytest.raises(ValueError, match="hashed distribution required"):
        bind_distribution({}, candidate_identity_sha256=identity["candidate_identity_sha256"], fit_sha256="99" * 32)


def test_bound_distribution_is_deterministic_and_authority_false():
    identity = build()
    distribution = {"distribution_sha256": "aa" * 32}
    a = bind_distribution(
        distribution,
        candidate_identity_sha256=identity["candidate_identity_sha256"],
        fit_sha256="99" * 32,
    )
    b = bind_distribution(
        distribution,
        candidate_identity_sha256=identity["candidate_identity_sha256"],
        fit_sha256="99" * 32,
    )
    assert a == b
    assert len(a["bound_distribution_sha256"]) == 64
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False
