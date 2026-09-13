import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NFL = ROOT / "sportsedge" / "sports" / "nfl"
EXPECTED_PREREG_BLOB = "f8487883186fc85b77f4e632b1aa710327473b8a"
EXPECTED_V1_REFERENCE_BLOB = "29f351d7ca37346795a8ce8e3cca8b01eda7914e"
EXPECTED_LEDGER_BLOB = "14022680891de3c3d73013ffabc8aee4611e86e6"
EXPECTED_PROPOSAL_BLOB = "2109c6d7546bbbed2b5c587eb13fd52d9325f488"
APPROVED_POLICY = "MODERN_REG_2018_2025"


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


class TestNFLV2KReferenceV2Activation(unittest.TestCase):
    def test_frozen_v1_governance_bytes_unchanged(self):
        self.assertEqual(git_blob_sha(NFL / "NFL_V2K_CLEAN_PREREG_2026-09-13.md"), EXPECTED_PREREG_BLOB)
        self.assertEqual(git_blob_sha(NFL / "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V1.json"), EXPECTED_V1_REFERENCE_BLOB)
        self.assertEqual(git_blob_sha(NFL / "NFL_V2K_ATTEMPT_LEDGER_V1.json"), EXPECTED_LEDGER_BLOB)

    def test_report_only_proposal_bytes_bound(self):
        proposal = NFL / "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2_PROPOSAL.json"
        self.assertEqual(git_blob_sha(proposal), EXPECTED_PROPOSAL_BLOB)
        data = json.loads(proposal.read_text())
        self.assertIsNone(data["selected_policy"])
        self.assertIsNone(data["review_decision"])
        self.assertFalse(data["implementation_admitted"])

    def test_v2_reference_is_frozen_to_human_selected_policy(self):
        ref = json.loads((NFL / "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2.json").read_text())
        self.assertEqual(ref["status"], "FROZEN_READY")
        self.assertEqual(ref["authority"], "REFERENCE_ONLY")
        self.assertEqual(ref["selected_policy"], APPROVED_POLICY)
        self.assertEqual(ref["absolute_mass_tolerance"], 0.005)
        self.assertEqual(ref["game_count"], 2127)
        self.assertEqual(set(ref["signed_margin_mass"]), {"-7", "-3", "3", "7"})
        self.assertTrue(ref["structural_improvement_gate"]["candidate_must_strictly_improve_calibration_slope_metric"])
        self.assertTrue(ref["structural_improvement_gate"]["candidate_must_strictly_improve_signed_key_mass_metric"])
        self.assertTrue(ref["structural_improvement_gate"]["absolute_per_key_tolerance_still_required"])
        self.assertFalse(ref["structural_improvement_gate"]["either_dimension_alone_counts_as_pass"])
        self.assertTrue(ref["structural_improvement_gate"]["ci_does_not_relax_absolute_mass_tolerance"])

    def test_admission_is_research_only_and_consumes_no_attempt(self):
        ref_path = NFL / "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2.json"
        admission = json.loads((NFL / "NFL_V2K_IMPLEMENTATION_ADMISSION_V2.json").read_text())
        self.assertEqual(admission["status"], "ADMITTED_RESEARCH_IMPLEMENTATION_ONLY")
        self.assertTrue(admission["effective_only_when_merged_to_main"])
        self.assertTrue(admission["authority"]["research_implementation"])
        for key in ("model_p", "promotion", "staking", "pricing", "run_it", "official", "untouched_readout"):
            self.assertFalse(admission["authority"][key])
        self.assertEqual(admission["attempt_budget"]["attempts_used"], 0)
        self.assertFalse(admission["attempt_budget"]["attempt_consumed_by_activation"])
        self.assertEqual(
            admission["bindings"]["frozen_v2_reference_sha256"],
            hashlib.sha256(ref_path.read_bytes()).hexdigest(),
        )
        ledger = json.loads((NFL / "NFL_V2K_ATTEMPT_LEDGER_V1.json").read_text())
        self.assertEqual(ledger["attempts_used"], 0)
        self.assertFalse(ledger["untouched_readout_allowed"])

    def test_builder_binding_matches_committed_builder(self):
        builder = ROOT / "scripts" / "build_nfl_v2k_reference_v2_activation.py"
        builder_sha = hashlib.sha256(builder.read_bytes()).hexdigest()
        ref = json.loads((NFL / "NFL_V2K_EMPIRICAL_KEY_REFERENCE_V2.json").read_text())
        admission = json.loads((NFL / "NFL_V2K_IMPLEMENTATION_ADMISSION_V2.json").read_text())
        self.assertEqual(ref["source_provenance"]["activation_builder_sha256"], builder_sha)
        self.assertEqual(admission["bindings"]["activation_builder_sha256"], builder_sha)


if __name__ == "__main__":
    unittest.main()
