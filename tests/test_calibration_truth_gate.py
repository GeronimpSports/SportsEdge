import unittest

from sportsedge.core.validation.calibration_truth_gate import evaluate_calibration_truth_gate


def evidence(rows):
    bins = [
        {"bin": i, "n": n, "mean_probability": p, "empirical_rate": y, "abs_deviation": abs(y - p)}
        for i, (n, p, y) in enumerate(rows)
    ]
    return {"n": sum(row[0] for row in rows), "bins": bins}


class CalibrationTruthGateTests(unittest.TestCase):
    def test_perfect_grouped_calibration_passes(self):
        result = evaluate_calibration_truth_gate(evidence([
            (50, 0.20, 0.20), (50, 0.40, 0.40), (50, 0.60, 0.60), (50, 0.80, 0.80),
        ]))
        self.assertTrue(result.pass_gate)
        self.assertAlmostEqual(result.intercept, 0.0, places=8)
        self.assertAlmostEqual(result.slope, 1.0, places=8)
        self.assertAlmostEqual(result.ece, 0.0, places=12)

    def test_sample_minimum_is_fail_closed(self):
        result = evaluate_calibration_truth_gate(evidence([
            (40, 0.20, 0.20), (40, 0.40, 0.40), (40, 0.60, 0.60), (40, 0.80, 0.80),
        ]))
        self.assertFalse(result.pass_gate)
        self.assertEqual(result.reason, "CALIBRATION_SAMPLE_BELOW_MINIMUM")

    def test_ece_gate_is_independent(self):
        result = evaluate_calibration_truth_gate(
            evidence([(50, 0.20, 0.23), (50, 0.40, 0.43), (50, 0.60, 0.63), (50, 0.80, 0.83)]),
            slope_min=0.0,
            slope_max=10.0,
            intercept_abs_max=10.0,
        )
        self.assertFalse(result.pass_gate)
        self.assertEqual(result.reason, "CALIBRATION_ECE_EXCEEDS_LIMIT")
        self.assertAlmostEqual(result.ece, 0.03, places=12)

    def test_slope_gate_blocks_overconfident_shape(self):
        result = evaluate_calibration_truth_gate(
            evidence([(50, 0.20, 0.30), (50, 0.40, 0.45), (50, 0.60, 0.55), (50, 0.80, 0.70)]),
            ece_max=1.0,
            intercept_abs_max=10.0,
        )
        self.assertFalse(result.pass_gate)
        self.assertEqual(result.reason, "CALIBRATION_SLOPE_OUT_OF_RANGE")

    def test_intercept_gate_blocks_systematic_bias(self):
        result = evaluate_calibration_truth_gate(
            evidence([(50, 0.20, 0.25), (50, 0.40, 0.45), (50, 0.60, 0.65), (50, 0.80, 0.85)]),
            slope_min=0.0,
            slope_max=10.0,
            ece_max=1.0,
        )
        self.assertFalse(result.pass_gate)
        self.assertEqual(result.reason, "CALIBRATION_INTERCEPT_OUT_OF_RANGE")

    def test_bin_count_mismatch_raises(self):
        payload = evidence([(100, 0.25, 0.25), (100, 0.75, 0.75)])
        payload["n"] = 201
        with self.assertRaisesRegex(ValueError, "CALIBRATION_BIN_COUNT_MISMATCH"):
            evaluate_calibration_truth_gate(payload)

    def test_unidentified_recalibration_blocks(self):
        result = evaluate_calibration_truth_gate(evidence([(200, 0.50, 0.50)]))
        self.assertFalse(result.pass_gate)
        self.assertEqual(result.reason, "CALIBRATION_RECALIBRATION_UNIDENTIFIED")


if __name__ == "__main__":
    unittest.main()
