import unittest
from sportsedge.props_joint_stage3 import football_joint, mlb_joint
from sportsedge.props_event_stage4 import football_td, mlb_hr
from sportsedge.props_pit_stage5 import validate_pit_inputs
from sportsedge.props_validation_stage6 import validate_probability_rows
from sportsedge.props_market_binding_stage7 import bind_prop_market, NO_VIG_ONE_SIDED

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
 def test_invalid_football_pmfs_fail_closed(self):
  bad_pmfs=((.5,-.1,.6),(.5,float("nan"),.5),(.5,float("inf"),.5),(.2,.2))
  for pmf in bad_pmfs:
   with self.subTest(pmf=pmf), self.assertRaisesRegex(ValueError,"INVALID_PMF"):
    football_joint(sport="NFL",entity_id="p",volume_pmf=pmf,mode="rushing",efficiency={"yards_per_carry":4.5},paths=100)
 def test_invalid_mlb_pmfs_fail_closed(self):
  for pmf in ((-.1,1.1),(.4,.4)):
   with self.subTest(pmf=pmf), self.assertRaisesRegex(ValueError,"INVALID_PMF"):
    mlb_joint(entity_id="x",opportunity_pmf=pmf,role="hitter",rates={},paths=100)
 def test_invalid_football_efficiency_probabilities_fail_closed(self):
  cases=(
   ("passing",{"completion_rate":-0.2,"yards_per_attempt":7.0},"completion_rate"),
   ("passing",{"completion_rate":1.4,"yards_per_attempt":7.0},"completion_rate"),
   ("passing",{"completion_rate":float("nan"),"yards_per_attempt":7.0},"completion_rate"),
   ("receiving",{"catch_rate":float("inf"),"yards_per_target":8.0},"catch_rate"),
   ("receiving",{"catch_rate":1.1,"yards_per_target":8.0},"catch_rate"),
  )
  for mode,efficiency,name in cases:
   with self.subTest(mode=mode,name=name), self.assertRaisesRegex(ValueError,f"INVALID_PROBABILITY:{name}"):
    football_joint(sport="NFL",entity_id="p",volume_pmf=(0,0,0,1),mode=mode,efficiency=efficiency,paths=100)
 def test_invalid_mlb_rate_probabilities_fail_closed(self):
  for name,value in (("strikeout_rate",-0.2),("walk_rate",1.4),("hit_rate",float("nan")),("extra_base_hit_rate",float("inf"))):
   rates={"strikeout_rate":.2,"walk_rate":.1,"hit_rate":.25,"extra_base_hit_rate":.35}
   rates[name]=value
   with self.subTest(name=name), self.assertRaisesRegex(ValueError,f"INVALID_PROBABILITY:{name}"):
    mlb_joint(entity_id="x",opportunity_pmf=(0,0,0,1),role="hitter",rates=rates,paths=100)
 def test_probability_boundaries_remain_exact_not_clamped(self):
  zero=football_joint(sport="NFL",entity_id="q0",volume_pmf=(0,0,0,1),mode="passing",efficiency={"completion_rate":0.0,"yards_per_attempt":7.0},paths=100,seed=3)
  one=football_joint(sport="NFL",entity_id="q1",volume_pmf=(0,0,0,1),mode="passing",efficiency={"completion_rate":1.0,"yards_per_attempt":7.0},paths=100,seed=3)
  self.assertTrue(all(x["completions"]==0 for x in zero.paths))
  self.assertTrue(all(x["completions"]==x["pass_attempts"]==3 for x in one.paths))
  mlb_zero=mlb_joint(entity_id="m0",opportunity_pmf=(0,0,0,1),role="pitcher",rates={"strikeout_rate":0.0,"walk_rate":0.0,"hit_rate":0.0,"extra_base_hit_rate":0.0},paths=100,seed=4)
  mlb_one=mlb_joint(entity_id="m1",opportunity_pmf=(0,0,0,1),role="pitcher",rates={"strikeout_rate":1.0,"walk_rate":0.0,"hit_rate":0.0,"extra_base_hit_rate":0.0},paths=100,seed=4)
  self.assertTrue(all(x["pitcher_strikeouts"]==0 for x in mlb_zero.paths))
  self.assertTrue(all(x["pitcher_strikeouts"]==x["batters_faced"]==3 for x in mlb_one.paths))
 def test_separate_events(self):
  self.assertGreater(football_td(sport="NFL",entity_id="x",pit={"team_expected_touchdowns":3,"player_td_opportunity_share":.2}).probability_at_least_one,0)
  self.assertGreater(mlb_hr(entity_id="x",pit={"expected_plate_appearances":4.3,"hr_probability_per_pa":.06}).probability_at_least_one,0)
 def test_stage4_zero_event_boundaries_are_exact(self):
  td=football_td(sport="NFL",entity_id="zero",pit={"team_expected_touchdowns":0.0,"player_td_opportunity_share":1.0})
  hr=mlb_hr(entity_id="zero",pit={"expected_plate_appearances":4.0,"hr_probability_per_pa":0.0})
  unavailable=football_td(sport="CFB",entity_id="out",pit={"team_expected_touchdowns":4.0,"player_td_opportunity_share":.5,"availability_probability":0.0})
  for d in (td,hr,unavailable):
   self.assertEqual(d.probability_at_least_one,0.0)
   self.assertEqual(d.probabilities[0],1.0)
   self.assertTrue(all(p==0.0 for p in d.probabilities[1:]))
 def test_stage4_invalid_quantities_fail_closed(self):
  for value in (-1.0,float("nan"),float("inf")):
   with self.subTest(kind="team_td",value=value), self.assertRaisesRegex(ValueError,"INVALID_EVENT_QUANTITY:team_expected_touchdowns"):
    football_td(sport="NFL",entity_id="x",pit={"team_expected_touchdowns":value,"player_td_opportunity_share":.2})
   with self.subTest(kind="pa",value=value), self.assertRaisesRegex(ValueError,"INVALID_EVENT_QUANTITY:expected_plate_appearances"):
    mlb_hr(entity_id="x",pit={"expected_plate_appearances":value,"hr_probability_per_pa":.05})
 def test_stage4_invalid_probabilities_fail_closed(self):
  football_cases=(("player_td_opportunity_share",-0.1),("player_td_opportunity_share",1.1),("player_td_opportunity_share",float("nan")),("availability_probability",float("inf")))
  for name,value in football_cases:
   pit={"team_expected_touchdowns":3.0,"player_td_opportunity_share":.2,"availability_probability":1.0};pit[name]=value
   with self.subTest(kind="football",name=name), self.assertRaisesRegex(ValueError,f"INVALID_EVENT_PROBABILITY:{name}"):
    football_td(sport="NFL",entity_id="x",pit=pit)
  mlb_cases=(("hr_probability_per_pa",-0.1),("hr_probability_per_pa",1.1),("hr_probability_per_pa",float("nan")),("availability_probability",float("inf")))
  for name,value in mlb_cases:
   pit={"expected_plate_appearances":4.0,"hr_probability_per_pa":.05,"availability_probability":1.0};pit[name]=value
   with self.subTest(kind="mlb",name=name), self.assertRaisesRegex(ValueError,f"INVALID_EVENT_PROBABILITY:{name}"):
    mlb_hr(entity_id="x",pit=pit)
 def test_pit_fail_closed(self):
  with self.assertRaisesRegex(ValueError,"PIT_FIELDS_MISSING"):
   validate_pit_inputs("NFL",{"asof_ts":"2026-09-13T10:00:00+00:00"})
 def test_validation_chronological(self):
  rows=[{"event_start_ts":f"2026-01-{i:02d}T00:00:00+00:00","model_probability":.5,"outcome":i%2} for i in range(1,10)]
  r=validate_probability_rows(rows,min_n=5,ece_max=.6,max_bin_deviation_max=.6,slope_min=0.0,slope_max=2.0,intercept_abs_max=1.0)
  self.assertTrue(r.passed);self.assertEqual(r.authority,"RESEARCH_ONLY")
 def test_default_calibration_gate_can_fail(self):
  rows=[{"event_start_ts":f"2026-02-{i:02d}T00:00:00+00:00","model_probability":.5,"outcome":1.0} for i in range(1,10)]
  r=validate_probability_rows(rows,min_n=5,ece_max=.6,max_bin_deviation_max=.6)
  self.assertFalse(r.passed)
 def test_stage7_blocks_unvalidated_model(self):
  with self.assertRaisesRegex(ValueError,"BLOCKED_NO_VALIDATED_PROBABILITY_ENGINE"):
   bind_prop_market(sport="NFL",market="ANYTIME_TD",entity_id="x",model_probability=.62,offered_odds=-150,validation_passed=False)
 def test_one_sided_ev_without_invented_no_vig(self):
  b=bind_prop_market(sport="NFL",market="ANYTIME_TD",entity_id="x",model_probability=.62,offered_odds=-150,validation_passed=True)
  self.assertEqual(b.market_no_vig_probability,NO_VIG_ONE_SIDED);self.assertEqual(b.fair_american_odds,-163);self.assertGreater(b.expected_value_per_unit,0);self.assertFalse(b.official);self.assertFalse(b.staking_authority)
 def test_two_sided_devig_only_after_model_exists(self):
  b=bind_prop_market(sport="MLB",market="PITCHER_STRIKEOUTS",entity_id="p",model_probability=.58,offered_odds=-110,paired_other_side_odds=-110,validation_passed=True,line=5.5)
  self.assertAlmostEqual(b.market_no_vig_probability,.5,places=9)

if __name__=="__main__":unittest.main()
