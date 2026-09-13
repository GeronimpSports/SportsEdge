import unittest
from sportsedge.props_joint_stage3 import football_joint, mlb_joint
from sportsedge.props_event_stage4 import football_td, mlb_hr
from sportsedge.props_pit_stage5 import validate_pit_inputs
from sportsedge.props_validation_stage6 import validate_probability_rows

class PropsSweepTests(unittest.TestCase):
 def test_joint_deterministic_and_coherent(self):
  pmf=(0.0,0.0,0.2,0.8)
  a=football_joint(sport="NFL",entity_id="p",volume_pmf=pmf,mode="receiving",efficiency={"catch_rate":.7,"yards_per_target":8.0},paths=200,seed=7)
  b=football_joint(sport="NFL",entity_id="p",volume_pmf=pmf,mode="receiving",efficiency={"catch_rate":.7,"yards_per_target":8.0},paths=200,seed=7)
  self.assertEqual(a.sha256,b.sha256); self.assertTrue(all(x["receptions"]<=x["targets"] for x in a.paths))
 def test_market_rejected(self):
  with self.assertRaisesRegex(ValueError,"MARKET_INPUT_FORBIDDEN"):
   football_joint(sport="CFB",entity_id="p",volume_pmf=(.1,.9),mode="rushing",efficiency={"yards_per_carry":5,"line":50},paths=100)
 def test_mlb_pitcher_joint(self):
  d=mlb_joint(entity_id="x",opportunity_pmf=(0,0,0,1),role="pitcher",rates={"strikeout_rate":.3,"walk_rate":.1,"hit_rate":.2,"extra_base_hit_rate":.3},paths=100)
  self.assertIn("pitcher_strikeouts",d.paths[0])
 def test_separate_events(self):
  self.assertGreater(football_td(sport="NFL",entity_id="x",pit={"team_expected_touchdowns":3,"player_td_opportunity_share":.2}).probability_at_least_one,0)
  self.assertGreater(mlb_hr(entity_id="x",pit={"expected_plate_appearances":4.3,"hr_probability_per_pa":.06}).probability_at_least_one,0)
 def test_pit_fail_closed(self):
  with self.assertRaisesRegex(ValueError,"PIT_FIELDS_MISSING"):
   validate_pit_inputs("NFL",{"asof_ts":"2026-09-13T10:00:00+00:00"})
 def test_validation_chronological(self):
  rows=[{"event_start_ts":f"2026-01-{i:02d}T00:00:00+00:00","model_probability":.5,"outcome":i%2} for i in range(1,10)]
  r=validate_probability_rows(rows,min_n=5,ece_max=.6,max_bin_deviation_max=.6);self.assertTrue(r.passed);self.assertEqual(r.authority,"RESEARCH_ONLY")

if __name__=="__main__":unittest.main()
