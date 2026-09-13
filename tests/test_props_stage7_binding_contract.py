import unittest

from sportsedge.props_market_binding_stage7 import (
    NO_VIG_ONE_SIDED,
    STATUS_RESEARCH,
    american_to_decimal,
    bind_prop_market,
    proportional_devig,
)


class PropsStage7BindingContractTests(unittest.TestCase):
    def test_validation_authority_must_be_literal_true(self):
        for value in (False,None,0,1,"true","false",[],{}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BLOCKED_NO_VALIDATED_PROBABILITY_ENGINE"):
                bind_prop_market(sport="NFL",market="ANYTIME_TD",entity_id="p",model_probability=.6,offered_odds=-110,validation_passed=value)

    def test_offered_odds_require_actual_integer_american_price(self):
        for value in ("-110",-110.5,True,False,0,99,-99,50,-50):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BAD_AMERICAN_ODDS"):
                bind_prop_market(sport="NFL",market="RECEPTIONS",entity_id="p",model_probability=.55,offered_odds=value,validation_passed=True,line=3.5)
        self.assertAlmostEqual(american_to_decimal(-100),2.0)
        self.assertAlmostEqual(american_to_decimal(100),2.0)

    def test_paired_side_uses_same_strict_price_contract(self):
        for value in ("-110",-110.5,True,0,75,-75):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BAD_AMERICAN_ODDS"):
                bind_prop_market(sport="MLB",market="PITCHER_STRIKEOUTS",entity_id="p",model_probability=.58,offered_odds=-110,paired_other_side_odds=value,validation_passed=True,line=5.5)

    def test_market_line_must_be_finite_numeric_not_bool_or_string(self):
        for value in (True,False,"5.5",float("nan"),float("inf"),float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BAD_MARKET_LINE"):
                bind_prop_market(sport="NFL",market="RUSHING_YARDS",entity_id="p",model_probability=.55,offered_odds=-110,validation_passed=True,line=value)

    def test_model_probability_must_be_finite_and_interior(self):
        for value in (0.0,1.0,-.1,1.1,float("nan"),float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BAD_MODEL_PROBABILITY"):
                bind_prop_market(sport="NFL",market="ANYTIME_TD",entity_id="p",model_probability=value,offered_odds=-110,validation_passed=True)

    def test_valid_one_sided_binding_preserves_unavailable_no_vig_and_zero_authority(self):
        bound=bind_prop_market(sport="NFL",market="ANYTIME_TD",entity_id="p",model_probability=.62,offered_odds=-150,validation_passed=True)
        self.assertEqual(bound.market_no_vig_probability,NO_VIG_ONE_SIDED)
        self.assertEqual(bound.offered_odds,-150)
        self.assertEqual(bound.status,STATUS_RESEARCH)
        self.assertFalse(bound.official)
        self.assertFalse(bound.staking_authority)
        self.assertGreater(bound.expected_value_per_unit,0.0)

    def test_valid_two_sided_binding_devigs_without_changing_authority(self):
        bound=bind_prop_market(sport="MLB",market="PITCHER_STRIKEOUTS",entity_id="p",model_probability=.58,offered_odds=-110,paired_other_side_odds=-110,validation_passed=True,line=5)
        self.assertAlmostEqual(bound.market_no_vig_probability,.5,places=12)
        self.assertEqual(bound.line,5.0)
        self.assertFalse(bound.official)
        self.assertFalse(bound.staking_authority)
        self.assertEqual(proportional_devig(-110,-110),(.5,.5))


if __name__=="__main__":
    unittest.main()
