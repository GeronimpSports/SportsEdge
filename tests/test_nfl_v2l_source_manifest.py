import pytest

from sportsedge.sports.nfl.v2l_source_manifest import build_source_manifest


H = "a" * 64
P = "b" * 64


def row(**updates):
    item = {
        "name": "pbp_2020_week_01.parquet",
        "source_identifier": "nflverse://pbp/2020/01",
        "season_scope": [2020],
        "week_scope": [1],
        "retrieved_at_utc": "2026-09-13T12:00:00Z",
        "byte_sha256": H,
        "parser_code_sha256": P,
    }
    item.update(updates)
    return item


def test_manifest_is_deterministic_and_requires_offense_defense_identity():
    a = build_source_manifest([row()], dataset_version="nflverse-2026-09-13")
    b = build_source_manifest([row()], dataset_version="nflverse-2026-09-13")
    assert a["manifest_sha256"] == b["manifest_sha256"]
    assert a["required_training_identity_fields"] == ["posteam", "defteam"]
    assert a["model_p_authority"] is False
    assert a["promotion_authority"] is False
    assert a["official_authority"] is False


def test_manifest_canonicalizes_aware_timestamp_to_utc():
    manifest = build_source_manifest(
        [row(retrieved_at_utc="2026-09-13T07:00:00-05:00")],
        dataset_version="nflverse-2026-09-13",
    )
    assert manifest["files"][0]["retrieved_at_utc"] == "2026-09-13T12:00:00Z"


def test_manifest_blocks_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_source_manifest(
            [row(retrieved_at_utc="2026-09-13T12:00:00")],
            dataset_version="nflverse-2026-09-13",
        )


def test_manifest_blocks_non_sha256_lineage():
    with pytest.raises(ValueError, match="byte_sha256 must be SHA256"):
        build_source_manifest(
            [row(byte_sha256="not-a-sha")],
            dataset_version="nflverse-2026-09-13",
        )


def test_manifest_requires_pinned_dataset_version_and_rows():
    with pytest.raises(ValueError, match="files and pinned dataset version required"):
        build_source_manifest([], dataset_version="nflverse-2026-09-13")
    with pytest.raises(ValueError, match="files and pinned dataset version required"):
        build_source_manifest([row()], dataset_version="")
