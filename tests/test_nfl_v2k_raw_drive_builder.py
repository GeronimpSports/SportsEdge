import unittest

from sportsedge.sports.nfl.v2k_raw_drive_builder import (
    build_drive_rows,
    normalize_fixed_drive_result,
    normalize_start_yard,
    provenance_contract,
)


class NFLV2KRawDriveBuilderTests(unittest.TestCase):
    def test_yardline_100_normalization_is_exact(self):
        self.assertEqual(normalize_start_yard(80), 20.0)
        self.assertEqual(normalize_start_yard(25), 75.0)
        for value in (0, 100, None, "bad"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_start_yard(value)

    def test_fixed_drive_result_mapping_is_explicit(self):
        expected = {
            "Touchdown": "TD",
            "Field goal": "FG",
            "Turnover": "TURNOVER",
            "Turnover on downs": "TURNOVER",
            "Punt": "PUNT_OTHER",
            "Missed field goal": "PUNT_OTHER",
            "End of half": "PUNT_OTHER",
            "Safety": "SAFETY",
            "Opp touchdown": "DEF_ST_TD",
        }
        for raw, normalized in expected.items():
            self.assertEqual(normalize_fixed_drive_result(raw), normalized)
        with self.assertRaisesRegex(ValueError, "UNMAPPED"):
            normalize_fixed_drive_result("Mystery")

    def test_builds_one_row_per_fixed_drive_and_skips_kickoff_start(self):
        rows = [
            {"game_id":"2025_01_A_B","fixed_drive":1,"fixed_drive_result":"Punt","play_id":1,"posteam":"A","defteam":"B","play_type":"kickoff","yardline_100":100},
            {"game_id":"2025_01_A_B","fixed_drive":1,"fixed_drive_result":"Punt","play_id":10,"posteam":"A","defteam":"B","play_type":"run","yardline_100":75},
            {"game_id":"2025_01_A_B","fixed_drive":1,"fixed_drive_result":"Punt","play_id":20,"posteam":"A","defteam":"B","play_type":"pass","yardline_100":66},
            {"game_id":"2025_01_A_B","fixed_drive":2,"fixed_drive_result":"Field goal","play_id":30,"posteam":"B","defteam":"A","play_type":"run","yardline_100":82},
        ]
        out = build_drive_rows(rows, kickoff_by_game={"2025_01_A_B":"2025-09-07T17:00:00Z"})
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].drive_id, "1")
        self.assertEqual(out[0].start_yard, 25.0)
        self.assertEqual(out[0].outcome, "PUNT_OTHER")
        self.assertEqual(out[1].start_yard, 18.0)
        self.assertEqual(out[1].outcome, "FG")

    def test_missing_scrimmage_start_blocks_instead_of_guessing(self):
        rows = [
            {"game_id":"g","fixed_drive":1,"fixed_drive_result":"Touchdown","play_id":1,"posteam":"A","defteam":"B","play_type":"kickoff","yardline_100":100},
        ]
        with self.assertRaisesRegex(ValueError, "DRIVE_START_UNRESOLVED"):
            build_drive_rows(rows, kickoff_by_game={"g":"2025-09-07T17:00:00Z"})

    def test_ambiguous_identity_or_result_blocks(self):
        base = [
            {"game_id":"g","fixed_drive":1,"fixed_drive_result":"Punt","play_id":10,"posteam":"A","defteam":"B","play_type":"run","yardline_100":75},
        ]
        bad_identity = base + [dict(base[0], play_id=11, posteam="C")]
        with self.assertRaisesRegex(ValueError, "IDENTITY_AMBIGUOUS"):
            build_drive_rows(bad_identity, kickoff_by_game={"g":"2025-09-07T17:00:00Z"})
        bad_result = base + [dict(base[0], play_id=11, fixed_drive_result="Touchdown")]
        with self.assertRaisesRegex(ValueError, "RESULT_AMBIGUOUS"):
            build_drive_rows(bad_result, kickoff_by_game={"g":"2025-09-07T17:00:00Z"})

    def test_sportsbook_fields_cannot_change_drive_rows(self):
        rows = [
            {"game_id":"g","fixed_drive":1,"fixed_drive_result":"Turnover","play_id":10,"posteam":"A","defteam":"B","play_type":"pass","yardline_100":60},
        ]
        a = build_drive_rows(rows, kickoff_by_game={"g":"2025-09-07T17:00:00Z"})
        contaminated = [dict(rows[0], spread_line=-7.5, total_line=48.5, money_pct=90, capper_pick="A")]
        b = build_drive_rows(contaminated, kickoff_by_game={"g":"2025-09-07T17:00:00Z"})
        self.assertEqual(a, b)
        self.assertEqual(provenance_contract()["sportsbook_fields_consumed"], [])

    def test_provenance_contract_carries_no_authority(self):
        p = provenance_contract()
        self.assertEqual(p["normalized_start_yard_formula"], "100 - yardline_100")
        self.assertFalse(p["model_fit_invoked"])
        self.assertFalse(p["evaluation_invoked"])
        self.assertFalse(p["readout_consumed"])
        self.assertFalse(p["model_p_authority"])
        self.assertFalse(p["promotion_authority"])
        self.assertFalse(p["official_authority"])


if __name__ == "__main__":
    unittest.main()
