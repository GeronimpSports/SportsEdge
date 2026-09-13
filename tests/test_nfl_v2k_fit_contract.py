import pytest

from sportsedge.sports.nfl.v2k_fit_contract import DriveRow, fit_pit, params_from_fit

MANIFEST = "a" * 64
CODE = "abcdef123456"


def rows():
    return [
        DriveRow("g1", "2025-09-01T17:00:00Z", "A", 25, "TD"),
        DriveRow("g1", "2025-09-01T17:00:00Z", "A", 30, "PUNT_OTHER"),
        DriveRow("g2", "2025-09-08T17:00:00Z", "A", 20, "FG"),
        DriveRow("g2", "2025-09-08T17:00:00Z", "A", 35, "TURNOVER"),
        DriveRow("g2", "2025-09-08T17:00:00Z", "A", 40, "PUNT_OTHER"),
        DriveRow("g2", "2025-09-08T17:00:00Z", "A", 22, "TD"),
    ]


def test_future_row_is_hard_pit_failure():
    bad = rows() + [DriveRow("future", "2026-09-13T17:00:00Z", "A", 25, "TD")]
    with pytest.raises(ValueError, match="PIT violation"):
        fit_pit(bad, prediction_cutoff_utc="2026-09-13T16:00:00Z", source_manifest_sha256=MANIFEST, code_sha=CODE)


def test_train_serve_binding_rejects_manifest_or_code_drift():
    fit = fit_pit(rows(), prediction_cutoff_utc="2026-01-01T00:00:00Z", source_manifest_sha256=MANIFEST, code_sha=CODE)
    params_from_fit(fit, expected_source_manifest_sha256=MANIFEST, expected_code_sha=CODE)
    with pytest.raises(ValueError, match="source manifest mismatch"):
        params_from_fit(fit, expected_source_manifest_sha256="b" * 64, expected_code_sha=CODE)
    with pytest.raises(ValueError, match="code SHA mismatch"):
        params_from_fit(fit, expected_source_manifest_sha256=MANIFEST, expected_code_sha="deadbeef")


def test_fit_never_grants_authority():
    fit = fit_pit(rows(), prediction_cutoff_utc="2026-01-01T00:00:00Z", source_manifest_sha256=MANIFEST, code_sha=CODE)
    assert fit["model_p_authority"] is False
    assert fit["promotion_authority"] is False
    assert fit["official_authority"] is False
    assert len(fit["fit_sha256"]) == 64
