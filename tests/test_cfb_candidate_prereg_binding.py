import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sportsedge.sports.cfb.candidate_prereg_binding import verify_candidate_prereg_binding

ROOT = Path(__file__).resolve().parents[1]


class TestCFBCandidatePreregBinding(unittest.TestCase):
    def test_repository_candidate_prereg_is_byte_and_semantically_bound(self):
        out = verify_candidate_prereg_binding(root=ROOT)
        self.assertEqual(out["status"], "READY_FOR_FIRST_EVALUATION")
        self.assertEqual(out["attempts_consumed"], 0)
        self.assertEqual(out["blockers"], [])
        self.assertFalse(out["evaluation_performed"])
        self.assertFalse(out["attempt_consumed_by_this_verifier"])
        self.assertFalse(out["model_p_created"])
        self.assertFalse(out["promotion_authority"])
        self.assertFalse(out["eligibility_changed"])
        self.assertFalse(out["official_authority"])

    def test_spec_mutation_breaks_binding(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            for rel in (
                "config/cfb_model_selection_policy_v1.json",
                "config/cfb_model_candidate_prereg_v1.json",
                "config/cfb_model_candidate_code_manifest_v1.json",
                "config/cfb_model_candidate_specs_v1.json",
            ):
                target = temp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, target)
            manifest = json.loads((temp / "config/cfb_model_candidate_code_manifest_v1.json").read_text())
            for rel in manifest["git_blob_identities"]:
                target = temp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, target)
            spec_path = temp / "config/cfb_model_candidate_specs_v1.json"
            spec = json.loads(spec_path.read_text())
            spec["candidates"]["PRIOR_CURRENT_BLEND"]["weighting_blending_constants"]["prior_equivalent_games"] = 5.0
            spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
            out = verify_candidate_prereg_binding(root=temp)
            self.assertEqual(out["status"], "BLOCKED_PREREG_BINDING")
            self.assertIn("SPEC_BUNDLE_SHA256_MISMATCH", out["blockers"])


if __name__ == "__main__":
    unittest.main()
