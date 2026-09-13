import pytest

from sportsedge.sports.nfl.v2k_fit_contract import DriveRow, fit_pit, params_from_fit

MANIFEST = "a" * 64
FEATURE_POLICY = "c" * 64
CODE = "abcdef123456"


def rows():
    return [
        DriveRow("g1", "1", "2025-09-01T17:00:00Z", "A", "B", 25, "TD"),
        DriveRow("g1", "2", "2025-09-01T17:00:00Z", "A", "B", 30, "PUNT_OTHER"),
        DriveRow("g2", "1", "2025-09-08T17:00:00Z", "A", "C", 20, "FG"),
        DriveRow("g2", "2", "2025-09-08T17:00:00Z", "A", "C", 35, "TURNOVER"),
        DriveRow("g2", "3", "2025-09-08T17:00:00Z", "A", "C", 40, "PUNT_OTHER"),
        DriveRow("g2", "4", "2025-09-08T17:00:00Z", "A", "C", 22, "TD"),
    ]


def fit(**overrides):
    kwargs = dict(
        prediction_cutoff_utc="2026-01-01T00:00:00Z",
        source_manifest_sha256=MANIFEST,
        feature_policy_sha256=FEATURE_POLICY,
        code_sha=CODE,
    )
    kwargs.update(overrides)
    return fit_pit(rows(), **kwargs)


def test_future_row_is_hard_pit_failure():
    bad = rows() + [DriveRow("future", "1", "2026-09-13T17:00:00Z", "A", "B", 25, "TD")]
    with pytest.raises(ValueError, match="PIT violation"):
        fit_pit(
            bad,
            prediction_cutoff_utc="2026-09-13T16:00:00Z",
            source_manifest_sha256=MANIFEST,
            feature_policy_sha256=FEATURE_POLICY,
            code_sha=CODE,
        )


def test_duplicate_drive_identity_is_hard_failure():
    dup = rows() + [DriveRow("g1", "1", "2025-09-01T17:00:00Z", "B", "A", 30, "PUNT_OTHER")]
    with pytest.raises(ValueError, match="duplicate drive identity"):
        fit_pit(dup, prediction_cutoff_utc="2026-01-01T00:00:00Z", source_manifest_sha256=MANIFEST, feature_policy_sha256=FEATURE_POLICY, code_sha=CODE)


def test_offense_and_defense_must_differ():
    bad = [DriveRow("g1", "1", "2025-09-01T17:00:00Z", "A", "A", 25, "TD")]
    with pytest.raises(ValueError, match="must differ"):
        fit_pit(bad, prediction_cutoff_utc="2026-01-01T00:00:00Z", source_manifest_sha256=MANIFEST, feature_policy_sha256=FEATURE_POLICY, code_sha=CODE)


def test_train_serve_binding_rejects_manifest_feature_policy_or_code_drift():
    fitted = fit()
    params_from_fit(fitted, expected_source_manifest_sha256=MANIFEST, expected_feature_policy_sha256=FEATURE_POLICY, expected_code_sha=CODE)
    with pytest.raises(ValueError, match="source manifest mismatch"):
        params_from_fit(fitted, expected_source_manifest_sha256="b" * 64, expected_feature_policy_sha256=FEATURE_POLICY, expected_code_sha=CODE)
    with pytest.raises(ValueError, match="feature policy mismatch"):
        params_from_fit(fitted, expected_source_manifest_sha256=MANIFEST, expected_feature_policy_sha256="d" * 64, expected_code_sha=CODE)
    with pytest.raises(ValueError, match="code SHA mismatch"):
        params_from_fit(fitted, expected_source_manifest_sha256=MANIFEST, expected_feature_policy_sha256=FEATURE_POLICY, expected_code_sha="deadbeef")


def test_fit_requires_immutable_feature_policy_identity():
    with pytest.raises(ValueError, match="feature policy identity"):
        fit(feature_policy_sha256="short")


def test_fit_never_grants_authority():
    fitted = fit()
    assert fitted["feature_policy_sha256"] == FEATURE_POLICY
    assert fitted["training_unique_drives"] == fitted["training_rows"]
    assert fitted["model_p_authority"] is False
    assert fitted["promotion_authority"] is False
    assert fitted["official_authority"] is False
    assert len(fitted["fit_sha256"]) == 64
