from sportsedge.sports.nfl.v2k_drive_simulator import DriveOutcome, V2KParams, simulate_distribution


def params():
    return V2KParams(
        drives_mean=10.5, drives_sd=1.2,
        start_yard_mean=27.0, start_yard_sd=9.0,
        shared_efficiency_sd=0.12,
        outcome_probs={
            DriveOutcome.TD.value: .22,
            DriveOutcome.FG.value: .15,
            DriveOutcome.SAFETY.value: .005,
            DriveOutcome.DEF_ST_TD.value: .005,
            DriveOutcome.TURNOVER.value: .14,
            DriveOutcome.PUNT_OTHER.value: .48,
        },
    )


def test_v2k_is_deterministic_and_fail_closed():
    a = simulate_distribution(params(), params(), n=250, seed=7)
    b = simulate_distribution(params(), params(), n=250, seed=7)
    assert a == b
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False
    assert set(a["signed_key_mass"]) == {"-7", "-3", "3", "7"}


def test_v2k_seed_changes_distribution_hash():
    a = simulate_distribution(params(), params(), n=250, seed=7)
    b = simulate_distribution(params(), params(), n=250, seed=8)
    assert a["distribution_sha256"] != b["distribution_sha256"]


def test_v2k_rejects_bad_taxonomy():
    p = params()
    bad = V2KParams(p.drives_mean, p.drives_sd, p.start_yard_mean, p.start_yard_sd, p.shared_efficiency_sd, {"TD": 1.0})
    try:
        simulate_distribution(bad, p, n=2)
    except ValueError as exc:
        assert "taxonomy" in str(exc)
    else:
        raise AssertionError("bad taxonomy must fail closed")
