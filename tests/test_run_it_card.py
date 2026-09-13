import unittest

from sportsedge.run_it_card import bettor_card_rows


class BettorCardVisibilityTests(unittest.TestCase):
    def test_only_official_rows_are_bettor_facing(self):
        rows = [
            {"market": "MONEYLINE", "bet_status": "OFFICIAL_BET", "model_p": 0.61},
            {"market": "SPREAD", "bet_status": "BLOCKED", "model_p": 0.58},
            {"market": "TOTAL", "bet_status": "PASS", "model_p": 0.57},
        ]
        card = bettor_card_rows(rows)
        self.assertEqual([row["market"] for row in card], ["MONEYLINE"])
        self.assertTrue(card[0]["bettor_card_presence"])

    def test_predictive_fail_cannot_surface_even_if_mislabeled_official(self):
        rows = [{
            "market": "SPREAD",
            "bet_status": "OFFICIAL_BET",
            "predictive_gate": "FAIL",
            "candidate_status": "PAPER",
            "stake_units": 0.0,
        }]
        self.assertEqual(bettor_card_rows(rows), [])

    def test_rejected_or_paper_candidate_cannot_surface(self):
        for field, value in (
            ("candidate_status", "PAPER"),
            ("candidate_state", "REJECTED"),
            ("research_status", "EVIDENCE_BLOCKED"),
            ("model_state", "NO_ENGINE"),
        ):
            with self.subTest(field=field, value=value):
                row = {"bet_status": "OFFICIAL_BET", field: value}
                self.assertEqual(bettor_card_rows([row]), [])

    def test_predictive_pass_official_row_may_surface(self):
        rows = [{
            "market": "TOTAL",
            "bet_status": "OFFICIAL_BET",
            "predictive_gate": "PASS",
            "stake_units": 0.5,
        }]
        card = bettor_card_rows(rows)
        self.assertEqual(len(card), 1)
        self.assertEqual(card[0]["market"], "TOTAL")

    def test_nonpositive_or_invalid_stake_is_not_playable(self):
        for stake in (0, -0.25, "bad"):
            with self.subTest(stake=stake):
                self.assertEqual(
                    bettor_card_rows([{"bet_status": "OFFICIAL_BET", "stake_units": stake}]),
                    [],
                )

    def test_explicit_visibility_veto_wins(self):
        row = {"bet_status": "OFFICIAL_BET", "bettor_card_presence": False}
        self.assertEqual(bettor_card_rows([row]), [])

    def test_input_rows_are_not_mutated(self):
        row = {"market": "MONEYLINE", "bet_status": "OFFICIAL_BET"}
        bettor_card_rows([row])
        self.assertNotIn("bettor_card_presence", row)


if __name__ == "__main__":
    unittest.main()
