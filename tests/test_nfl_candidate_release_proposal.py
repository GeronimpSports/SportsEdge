import unittest

from sportsedge.sports.nfl.candidate_release_proposal import (
    NFLCandidateReleaseProposalError,
    PROPOSAL_STATUS,
    build_candidate_release_proposal,
)
from sportsedge.sports.nfl.m2 import PRODUCTION_NFL_M2_MODEL_ID


MODEL_ID = "fixture_v2_candidate"
DISTRIBUTION = "FIXTURE_V2_DISTRIBUTION_V1"
PREREG_SHA = "a" * 64
READOUT_SHA = "b" * 64
SOURCE_SHA = "c" * 64
CODE_SHA = "d" * 40


def readout():
    return {
        "status": "FIRST_READOUT_DIAGNOSTIC_ONLY",
        "preregistration_locked": True,
        "post_readout_retuning_allowed": False,
        "promotion_eligible": False,
        "promotion_authority": False,
        "model_p_authority": False,
        "official_status_granted": False,
        "production_registry_consumes_this_artifact": False,
        "model_id": MODEL_ID,
        "distribution_contract": DISTRIBUTION,
        "source_manifest_sha256": SOURCE_SHA,
    }


def proposal(**overrides):
    kwargs = {
        "candidate_model_id": MODEL_ID,
        "distribution_contract": DISTRIBUTION,
        "preregistration_sha256": PREREG_SHA,
        "first_readout_sha256": READOUT_SHA,
        "source_manifest_sha256": SOURCE_SHA,
        "code_git_sha": CODE_SHA,
        "readout": readout(),
    }
    kwargs.update(overrides)
    return build_candidate_release_proposal(**kwargs)


class NFLCandidateReleaseProposalTests(unittest.TestCase):
    def test_proposal_binds_identity_but_grants_zero_authority(self):
        out = proposal()
        self.assertEqual(out["status"], PROPOSAL_STATUS)
        self.assertEqual(out["candidate_identity"]["model_id"], MODEL_ID)
        self.assertEqual(out["candidate_identity"]["distribution_contract"], DISTRIBUTION)
        self.assertEqual(out["candidate_identity"]["code_git_sha"], CODE_SHA)
        self.assertEqual(out["evidence_identity"]["preregistration_sha256"], PREREG_SHA)
        self.assertEqual(out["evidence_identity"]["first_readout_sha256"], READOUT_SHA)
        self.assertEqual(out["evidence_identity"]["source_manifest_sha256"], SOURCE_SHA)
        self.assertIsNone(out["human_review"]["review_decision"])
        self.assertIsNone(out["human_review"]["selected_production_release_id"])
        self.assertFalse(out["human_review"]["implementation_admitted"])
        self.assertTrue(out["authority"])
        self.assertTrue(all(value is False for value in out["authority"].values()))

    def test_legacy_production_m2_cannot_be_relabelled_as_candidate_release(self):
        raw = readout()
        raw["model_id"] = PRODUCTION_NFL_M2_MODEL_ID
        with self.assertRaisesRegex(
            NFLCandidateReleaseProposalError,
            "NFL_CANDIDATE_RELEASE_LEGACY_M2_RELABEL_PROHIBITED",
        ):
            proposal(candidate_model_id=PRODUCTION_NFL_M2_MODEL_ID, readout=raw)

    def test_identity_mismatches_fail_closed(self):
        cases = (
            ("model_id", "other", "READOUT_MODEL_ID_MISMATCH"),
            ("distribution_contract", "other", "READOUT_DISTRIBUTION_MISMATCH"),
            ("source_manifest_sha256", "e" * 64, "READOUT_SOURCE_MISMATCH"),
        )
        for field, value, reason in cases:
            raw = readout()
            raw[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                NFLCandidateReleaseProposalError,
                reason,
            ):
                proposal(readout=raw)

    def test_readout_must_remain_preregistered_zero_authority(self):
        mutations = (
            ("preregistration_locked", False, "PREREG_LOCK_REQUIRED"),
            ("post_readout_retuning_allowed", True, "POST_READOUT_RETUNING_PROHIBITED"),
            ("promotion_eligible", True, "ZERO_AUTHORITY_REQUIRED:promotion_eligible"),
            ("promotion_authority", True, "ZERO_AUTHORITY_REQUIRED:promotion_authority"),
            ("model_p_authority", True, "ZERO_AUTHORITY_REQUIRED:model_p_authority"),
            ("official_status_granted", True, "ZERO_AUTHORITY_REQUIRED:official_status_granted"),
            ("production_registry_consumes_this_artifact", True, "ZERO_AUTHORITY_REQUIRED:production_registry_consumes_this_artifact"),
        )
        for field, value, reason in mutations:
            raw = readout()
            raw[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                NFLCandidateReleaseProposalError,
                reason,
            ):
                proposal(readout=raw)

    def test_hash_and_code_identities_are_strict(self):
        invalid = (
            ("preregistration_sha256", "a" * 63, "PREREG_SHA256_INVALID"),
            ("first_readout_sha256", "not-a-hash", "READOUT_SHA256_INVALID"),
            ("source_manifest_sha256", "z" * 64, "SOURCE_SHA256_INVALID"),
            ("code_git_sha", "d" * 39, "CODE_SHA_INVALID"),
        )
        for field, value, reason in invalid:
            with self.subTest(field=field), self.assertRaisesRegex(
                NFLCandidateReleaseProposalError,
                reason,
            ):
                proposal(**{field: value})


if __name__ == "__main__":
    unittest.main()
