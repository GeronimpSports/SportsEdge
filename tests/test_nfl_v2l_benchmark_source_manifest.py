import pytest

from sportsedge.sports.nfl.v2l_benchmark_source_manifest import build_benchmark_source_manifest


H = "c" * 64
P = "d" * 64


def capture(**updates):
    item = {
        "game_id": "2020_01_AWAY_HOME",
        "book": "draftkings",
        "source_identifier": "archive://closing-lines/2020_01_AWAY_HOME",
        "captured_at_utc": "2020-09-13T16:55:00Z",
        "raw_byte_sha256": H,
        "parser_code_sha256": P,
    }
    item.update(updates)
    return item


def test_manifest_is_deterministic_and_comparator_only():
    a = build_benchmark_source_manifest([capture()], provider_version="archive-v1")
    b = build_benchmark_source_manifest([capture()], provider_version="archive-v1")
    assert a["manifest_sha256"] == b["manifest_sha256"]
    assert a["role"] == "EVALUATION_COMPARATOR_ONLY"
    assert a["sportsbook_inputs_allowed_in_model_fit"] is False
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False


def test_manifest_canonicalizes_aware_timestamp_to_utc():
    manifest = build_benchmark_source_manifest(
        [capture(captured_at_utc="2020-09-13T11:55:00-05:00")],
        provider_version="archive-v1",
    )
    assert manifest["captures"][0]["captured_at_utc"] == "2020-09-13T16:55:00Z"


def test_manifest_blocks_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_benchmark_source_manifest(
            [capture(captured_at_utc="2020-09-13T16:55:00")],
            provider_version="archive-v1",
        )


def test_manifest_blocks_non_sha256_lineage():
    with pytest.raises(ValueError, match="raw_byte_sha256 must be SHA256"):
        build_benchmark_source_manifest(
            [capture(raw_byte_sha256="bad")],
            provider_version="archive-v1",
        )


def test_manifest_requires_provider_version_and_captures():
    with pytest.raises(ValueError, match="captures and provider version required"):
        build_benchmark_source_manifest([], provider_version="archive-v1")
    with pytest.raises(ValueError, match="captures and provider version required"):
        build_benchmark_source_manifest([capture()], provider_version="")
