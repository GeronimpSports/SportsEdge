from sportsedge.sports.nfl.v2k_source_acquisition_contract import (
    DEFAULT_SEASONS,
    build_acquisition_plan,
    canonical_pbp_url,
)


def test_canonical_url_is_nflverse_release_parquet():
    assert canonical_pbp_url(2025) == (
        "https://github.com/nflverse/nflverse-data/releases/download/"
        "pbp/play_by_play_2025.parquet"
    )


def test_plan_is_deterministic_and_fail_closed():
    a = build_acquisition_plan([2025, 2024, 2025])
    b = build_acquisition_plan([2024, 2025])
    assert a == b
    assert [o["season"] for o in a["objects"]] == [2024, 2025]
    assert a["requires_byte_sha256_after_download"] is True
    assert a["requires_retrieved_at_utc"] is True
    assert a["requires_parser_code_sha256"] is True
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False


def test_default_window_stops_before_2026_forward_outcomes():
    assert min(DEFAULT_SEASONS) == 2010
    assert max(DEFAULT_SEASONS) == 2025
    assert 2026 not in DEFAULT_SEASONS


def test_noncanonical_source_variants_are_rejected():
    import pytest
    with pytest.raises(ValueError):
        canonical_pbp_url(2025, dataset_tag="pbp_raw")
    with pytest.raises(ValueError):
        canonical_pbp_url(2025, file_format="csv")
    with pytest.raises(ValueError):
        build_acquisition_plan([])
