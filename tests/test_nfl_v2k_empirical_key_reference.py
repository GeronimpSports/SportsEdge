import hashlib
import json
import math
import unittest
from pathlib import Path

from scripts.build_nfl_v2k_empirical_key_reference import wilson95


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "sportsedge/sports/nfl/NFL_V2K_EMPIRICAL_KEY_REFERENCE_V1.json"
BUILDER = ROOT / "scripts/build_nfl_v2k_empirical_key_reference.py"
SIGNED_KEYS = (-7, -3, 3, 7)


class NflV2KEmpiricalKeyReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REFERENCE.read_text(encoding="utf-8"))

    def test_reference_is_frozen_ready_and_builder_bound(self):
        self.assertEqual(self.data["status"], "FROZEN_READY")
        ref = self.data["reference"]
        self.assertEqual(ref["game_count"], 2127)
        actual_builder_sha = hashlib.sha256(BUILDER.read_bytes()).hexdigest()
        self.assertEqual(ref["builder_code_sha256"], actual_builder_sha)
        self.assertEqual(
            ref["raw_source_sha256"],
            "902f1a3796d576ee846e2b54e99b46a5ab1bdd17bd34c93e8f9f1f797f61281e",
        )
        self.assertEqual(
            ref["evidence_artifact_digest"],
            "sha256:e53f16804c74ec197b23dd17180ad88d1c696d4a93e593ecc17fa8ccf480a437",
        )

    def test_reference_semantics_are_explicit(self):
        policy = self.data["reference_policy"]
        self.assertEqual((policy["season_type"], policy["first_season"], policy["last_season"]), ("REG", 2018, 2025))
        sign = policy["sign_convention"]
        self.assertEqual(sign["formula"], "home_final_score_minus_away_final_score")
        self.assertEqual(sign["neutral_site_games"], "INCLUDED_USING_OFFICIAL_SCHEDULE_HOME_AWAY_DESIGNATION")
        overtime = policy["overtime_policy"]
        self.assertTrue(overtime["games_included"])
        self.assertEqual(overtime["margin_quantity"], "FINAL_SCORE_INCLUDING_OVERTIME")
        self.assertFalse(overtime["regulation_margin_for_reference"])
        self.assertTrue(policy["structural_break_policy"]["silent_window_extension_forbidden"])

    def test_per_key_uncertainty_recomputes_exactly(self):
        ref = self.data["reference"]
        n = ref["game_count"]
        expected_counts = {-7: 89, -3: 143, 3: 164, 7: 92}
        for key in SIGNED_KEYS:
            row = ref["signed_margin_mass"][str(key)]
            self.assertEqual(row["count"], expected_counts[key])
            p = expected_counts[key] / n
            self.assertAlmostEqual(row["probability"], p, places=15)
            self.assertAlmostEqual(row["standard_error"], math.sqrt(p * (1.0 - p) / n), places=15)
            low, high = wilson95(expected_counts[key], n)
            self.assertAlmostEqual(row["ci95_low"], low, places=15)
            self.assertAlmostEqual(row["ci95_high"], high, places=15)

    def test_m2_control_metrics_recompute(self):
        ref = self.data["reference"]
        control = ref["control_metrics"]
        slope = control["calibration_slope"]
        self.assertAlmostEqual(control["calibration_slope_metric"], abs(slope - 1.0), places=15)
        rmse = math.sqrt(
            sum(
                (control["signed_key_probability"][str(k)] - ref["signed_margin_mass"][str(k)]["probability"]) ** 2
                for k in SIGNED_KEYS
            )
            / len(SIGNED_KEYS)
        )
        self.assertAlmostEqual(control["signed_key_mass_rmse"], rmse, places=15)
        self.assertEqual(control["control_identity"], "NFL_M2_FROZEN_CONTROL")
        self.assertEqual(control["calibration_gate_contract"], "SPORTSEDGE_CALIBRATION_TRUTH_GATE_V1")

    def test_joint_gate_cannot_pass_one_dimension(self):
        gate = self.data["joint_improvement_gate"]
        self.assertTrue(gate["required"])
        self.assertTrue(gate["candidate_must_strictly_improve_calibration_slope_metric"])
        self.assertTrue(gate["candidate_must_strictly_improve_signed_key_mass_metric"])
        self.assertFalse(gate["either_dimension_alone_counts_as_pass"])
        self.assertTrue(gate["absolute_per_key_tolerance_still_required"])
        uncertainty = self.data["uncertainty_policy"]
        self.assertTrue(uncertainty["reported_per_signed_key"])
        self.assertTrue(uncertainty["pooled_key_uncertainty_forbidden"])
        self.assertTrue(uncertainty["ci_does_not_relax_absolute_mass_tolerance"])

    def test_build_attestation_denies_leakage(self):
        att = self.data["build_attestation"]
        for key in (
            "games_sha256_verified",
            "manifest_file_sha256_verified",
            "manifest_schedule_anchor_verified",
            "production_validation_sha256_verified",
            "promotion_registry_sha256_verified",
        ):
            self.assertTrue(att[key])
        self.assertFalse(att["hand_entered_reference_values_used"])
        self.assertFalse(att["sportsbook_prices_used"])
        self.assertFalse(att["v2k_simulations_used"])


if __name__ == "__main__":
    unittest.main()
