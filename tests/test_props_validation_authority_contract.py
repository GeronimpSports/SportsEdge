from copy import deepcopy

import pytest

from sportsedge.props_validation_provenance_stage6 import (
    validation_attestation_sha256,
    verify_validation_attestation,
)


def _sealed(payload):
    out = deepcopy(payload)
    out["artifact_sha256"] = validation_attestation_sha256(out)
    return out


def _base_attestation():
    return {
        "schema_version": "PROP_VALIDATION_ATTESTATION_V1",
        "authority": "RESEARCH_ONLY",
        "status": "PASS",
        "passed": True,
        "market_prices_used_as_model_inputs": False,
        "can_create_model_p": False,
        "can_promote": False,
        "staking_authority": False,
        "official_authority": False,
    }


def test_zero_authority_attestation_verifies():
    verified = verify_validation_attestation(_sealed(_base_attestation()))
    assert verified["authority"] == "RESEARCH_ONLY"
    assert verified["passed"] is True


@pytest.mark.parametrize(
    "field",
    [
        "market_prices_used_as_model_inputs",
        "can_create_model_p",
        "can_promote",
        "staking_authority",
        "official_authority",
    ],
)
def test_hash_valid_authority_escalation_fails_closed(field):
    payload = _base_attestation()
    payload[field] = True
    with pytest.raises(ValueError, match=f"VALIDATION_ATTESTATION_AUTHORITY_FLAG_INVALID:{field}"):
        verify_validation_attestation(_sealed(payload))


def test_missing_or_string_false_authority_flag_fails_closed():
    missing = _base_attestation()
    missing.pop("can_promote")
    with pytest.raises(ValueError, match="VALIDATION_ATTESTATION_AUTHORITY_FLAG_INVALID:can_promote"):
        verify_validation_attestation(_sealed(missing))

    string_false = _base_attestation()
    string_false["can_promote"] = "false"
    with pytest.raises(ValueError, match="VALIDATION_ATTESTATION_AUTHORITY_FLAG_INVALID:can_promote"):
        verify_validation_attestation(_sealed(string_false))
