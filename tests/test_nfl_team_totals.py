import unittest

from sportsedge.sports.nfl.team_totals import (
    NFLTeamTotalError,
    price_nfl_team_totals,
    resolve_team_total_readiness,
)


class NFLTeamTotalPricingTests(unittest.TestCase):
    def test_prices_both_team_totals_from_same_score_distribution(self):
        distribution = [
            {"home_score": 24, "away_score": 17},
            {"home_score": 21, "away_score": 21},
            {"home_score": 27, "away_score": 14},
            {"home_score": 20, "away_score": 24},
        ]
        priced = price_nfl_team_totals(
            distribution,
            home_total_line=21.0,
            away_total_line=17.0,
        )
        self.assertEqual(priced["home_team_total"], {"over": 0.5, "under": 0.25, "push": 0.25})
        self.assertEqual(priced["away_team_total"], {"over": 0.5, "under": 0.25, "push": 0.25})

    def test_line_changes_do_not_modify_distribution(self):
        distribution = [
            {"home_score": 24, "away_score": 17},
            {"home_score": 20, "away_score": 23},
        ]
        before = [dict(row) for row in distribution]
        price_nfl_team_totals(distribution, home_total_line=20.5, away_total_line=20.5)
        self.assertEqual(distribution, before)

    def test_missing_score_fails_closed(self):
        with self.assertRaisesRegex(NFLTeamTotalError, "NFL_TEAM_TOTAL_SCORE_MISSING"):
            price_nfl_team_totals(
                [{"home_score": 24}],
                home_total_line=20.5,
                away_total_line=20.5,
            )


class NFLTeamTotalPromotionTests(unittest.TestCase):
    def test_deployed_game_total_does_not_promote_team_total(self):
        parent = {"stage": "DEPLOYED", "eligible": True}
        readiness = resolve_team_total_readiness(
            "HOME_TEAM_TOTAL",
            derivative_promotion_row=None,
            game_total_promotion_row=parent,
        )
        self.assertFalse(readiness.eligible)
        self.assertEqual(readiness.stage, "EVIDENCE_BLOCKED")
        self.assertFalse(readiness.inherited_from_game_total)

    def test_derivative_requires_its_own_deployed_evidence(self):
        readiness = resolve_team_total_readiness(
            "AWAY_TEAM_TOTAL",
            derivative_promotion_row={"stage": "CI_ATTESTED", "eligible": False},
            game_total_promotion_row={"stage": "DEPLOYED", "eligible": True},
        )
        self.assertFalse(readiness.eligible)
        self.assertEqual(readiness.stage, "CI_ATTESTED")

        deployed = resolve_team_total_readiness(
            "AWAY_TEAM_TOTAL",
            derivative_promotion_row={"stage": "DEPLOYED", "eligible": True},
        )
        self.assertTrue(deployed.eligible)
        self.assertEqual(deployed.reason, "TEAM_TOTAL_MARKET_SPECIFIC_PROMOTION_PASS")

    def test_stage_eligible_contradiction_fails_closed(self):
        with self.assertRaisesRegex(NFLTeamTotalError, "STAGE_CONTRADICTION"):
            resolve_team_total_readiness(
                "HOME_TEAM_TOTAL",
                derivative_promotion_row={"stage": "VALIDATED_MATH", "eligible": True},
            )


if __name__ == "__main__":
    unittest.main()
