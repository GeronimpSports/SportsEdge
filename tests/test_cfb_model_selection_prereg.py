import json,unittest
from pathlib import Path
from sportsedge.sports.cfb.model_selection_prereg import audit_model_selection_prereg
ROOT=Path(__file__).resolve().parents[1]
class TestCFBModelSelectionPrereg(unittest.TestCase):
 def policy(self):return json.loads((ROOT/"config/cfb_model_selection_policy_v1.json").read_text())
 def candidate(self,f):return {"family":f,"status":"PREREGISTERED_UNEVALUATED","formula":"frozen before evaluation","feature_list":["feature_a"],"weighting_blending_constants":{},"training_window":{"start_season":2015,"end_season":2025},"hyperparameter_policy":{"mode":"FROZEN"},"source_contract_identity":"CFBD_STATS_SEASON_ADVANCED_ENDWEEK_V1","code_sha256":"a"*64,"config_sha256":"b"*64}
 def complete(self):
  p=self.policy();return {"candidates":{f:self.candidate(f) for f in p["candidate_families_predeclared"]}}
 def test_missing_specs_blocks_without_spending_attempt(self):
  out=audit_model_selection_prereg(self.policy(),None);self.assertEqual(out["status"],"BLOCKED_PREREG_INCOMPLETE");self.assertEqual(out["attempts_consumed"],0);self.assertFalse(out["attempt_consumed_by_this_audit"]);self.assertFalse(out["model_p_created"])
 def test_all_four_executable_complete_specs_can_be_ready(self):
  out=audit_model_selection_prereg(self.policy(),self.complete());self.assertEqual(out["status"],"READY_FOR_FIRST_EVALUATION");self.assertEqual(len(out["implemented_families"]),4);self.assertTrue(all(x["executable"] and x["complete"] for x in out["candidate_results"]));self.assertFalse(out["attempt_consumed_by_this_audit"])
 def test_missing_hash_blocks(self):
  p=self.policy();x=self.complete();x["candidates"][p["candidate_families_predeclared"][0]]["code_sha256"]=None;out=audit_model_selection_prereg(p,x);self.assertEqual(out["status"],"BLOCKED_PREREG_INCOMPLETE");self.assertIn("CODE_SHA256_MISSING_OR_INVALID",out["candidate_results"][0]["blockers"])
 def test_result_leakage_is_forbidden(self):
  p=self.policy();x=self.complete();x["candidates"][p["candidate_families_predeclared"][0]]["rmse"]=1;out=audit_model_selection_prereg(p,x);self.assertIn("POST_EVALUATION_FIELD_PRESENT_IN_PREREGISTRATION",out["candidate_results"][0]["blockers"])
 def test_nonzero_attempts_cannot_claim_first_eval_readiness(self):
  p=self.policy();p["attempts_consumed"]=1;out=audit_model_selection_prereg(p,self.complete());self.assertEqual(out["status"],"BLOCKED_PREREG_INCOMPLETE");self.assertIn("FIRST_EVALUATION_GATE_REQUIRES_ZERO_ATTEMPTS_CONSUMED",out["blockers"])
if __name__=="__main__":unittest.main()
