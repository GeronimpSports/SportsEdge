import pytest

from sportsedge.sports.nfl.v2k_source_manifest import build_source_manifest

SHA_A = "a" * 64
SHA_B = "b" * 64


def raw(**changes):
    row = {
        "name": "pbp_2020.parquet",
        "source_identifier": "nflverse/releases/pbp/2020",
        "retrieved_at_utc": "2026-09-13T03:00:00Z",
        "season_scope": [2020],
        "week_scope": "ALL_REGULAR_AND_POSTSEASON",
        "byte_sha256": SHA_A,
        "parser_code_sha256": SHA_B,
    }
    row.update(changes)
    return row


def test_manifest_binds_required_raw_provenance():
    m = build_source_manifest([raw()], dataset_version="pinned-release-v1")
    f = m["files"][0]
    assert f["source_identifier"] == "nflverse/releases/pbp/2020"
    assert f["retrieved_at_utc"].endswith("+00:00")
    assert f["byte_sha256"] == SHA_A
    assert f["parser_code_sha256"] == SHA_B
    assert len(m["manifest_sha256"]) == 64
    assert m["model_p_authority"] is False and m["official_authority"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"source_identifier": ""},
        {"retrieved_at_utc": "2026-09-13T03:00:00"},
        {"season_scope": None},
        {"week_scope": None},
        {"byte_sha256": "short"},
        {"parser_code_sha256": "short"},
    ],
)
def test_manifest_blocks_incomplete_or_mutable_provenance(changes):
    with pytest.raises(ValueError):
        build_source_manifest([raw(**changes)], dataset_version="pinned-release-v1")
