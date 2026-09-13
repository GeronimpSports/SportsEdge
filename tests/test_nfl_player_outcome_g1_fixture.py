import json
import subprocess
import sys
import unittest


class NFLPlayerOutcomeG1FixtureTests(unittest.TestCase):
    def test_fixture_replay_is_byte_deterministic(self):
        cmd = [sys.executable, "scripts/run_nfl_player_outcome_g1_fixture.py"]
        first = subprocess.check_output(cmd)
        second = subprocess.check_output(cmd)
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertEqual(payload["status"], "RESEARCH_ONLY")
        self.assertFalse(payload["market_prices_consumed"])
        self.assertFalse(payload["random_split_used"])
        self.assertGreater(payload["probability_metrics"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
