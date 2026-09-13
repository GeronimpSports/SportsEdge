import math
import unittest

from sportsedge.props_validation_stage6 import validate_probability_rows


def permissive_validate(rows):
    return validate_probability_rows(
        rows,
        min_n=2,
        ece_max=1.0,
        max_bin_deviation_max=1.0,
        slope_min=-10.0,
        slope_max=10.0,
        intercept_abs_max=10.0,
    )


class PropsStage6ValidationContractTests(unittest.TestCase):
    def test_mixed_offsets_are_ordered_by_absolute_instant(self):
        rows=[
            {"event_start_ts":"2026-01-01T23:30:00+09:00","model_probability":0.2,"outcome":0},
            {"event_start_ts":"2026-01-01T10:00:00-05:00","model_probability":0.8,"outcome":1},
        ]
        result=permissive_validate(rows)
        self.assertTrue(result.chronological)

    def test_lexically_sorted_but_instant_reversed_is_rejected(self):
        rows=[
            {"event_start_ts":"2026-01-01T10:00:00-05:00","model_probability":0.2,"outcome":0},
            {"event_start_ts":"2026-01-01T14:30:00+00:00","model_probability":0.8,"outcome":1},
        ]
        with self.assertRaisesRegex(ValueError,"NON_CHRONOLOGICAL_VALIDATION_FORBIDDEN"):
            permissive_validate(rows)

    def test_naive_and_malformed_timestamps_fail_closed(self):
        base={"model_probability":0.5,"outcome":0}
        for timestamp,reason in (
            ("2026-01-01T12:00:00","VALIDATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE"),
            ("not-a-time","VALIDATION_TIMESTAMP_INVALID"),
        ):
            with self.subTest(timestamp=timestamp), self.assertRaisesRegex(ValueError,reason):
                permissive_validate([dict(base,event_start_ts=timestamp),dict(base,event_start_ts="2026-01-02T12:00:00+00:00")])

    def test_exact_zero_one_probabilities_stay_exact_for_non_log_metrics(self):
        rows=[
            {"event_start_ts":"2026-01-01T12:00:00+00:00","model_probability":0.0,"outcome":0},
            {"event_start_ts":"2026-01-02T12:00:00+00:00","model_probability":1.0,"outcome":1},
        ]
        result=validate_probability_rows(rows,min_n=2,ece_max=0.0,max_bin_deviation_max=0.0,slope_min=1.0,slope_max=1.0,intercept_abs_max=0.0)
        self.assertEqual(result.brier,0.0)
        self.assertEqual(result.ece,0.0)
        self.assertEqual(result.max_bin_deviation,0.0)
        self.assertEqual(result.calibration_slope,1.0)
        self.assertEqual(result.calibration_intercept,0.0)
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.log_loss,0.0)

    def test_any_quantity_mode_requires_complete_pairs_on_every_row(self):
        rows=[
            {"event_start_ts":"2026-01-01T12:00:00+00:00","model_probability":0.2,"outcome":0,"quantity_prediction":10.0,"quantity_actual":12.0},
            {"event_start_ts":"2026-01-02T12:00:00+00:00","model_probability":0.8,"outcome":1},
        ]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_QUANTITY_VALIDATION_ROW"):
            permissive_validate(rows)
        one_sided=[
            {"event_start_ts":"2026-01-01T12:00:00+00:00","model_probability":0.2,"outcome":0,"quantity_prediction":10.0},
            {"event_start_ts":"2026-01-02T12:00:00+00:00","model_probability":0.8,"outcome":1,"quantity_prediction":20.0,"quantity_actual":18.0},
        ]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_QUANTITY_VALIDATION_ROW"):
            permissive_validate(one_sided)

    def test_nonfinite_quantity_values_fail_closed(self):
        for value in (float("nan"),float("inf"),float("-inf")):
            rows=[
                {"event_start_ts":"2026-01-01T12:00:00+00:00","model_probability":0.2,"outcome":0,"quantity_prediction":value,"quantity_actual":10.0},
                {"event_start_ts":"2026-01-02T12:00:00+00:00","model_probability":0.8,"outcome":1,"quantity_prediction":20.0,"quantity_actual":18.0},
            ]
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,"BAD_QUANTITY_VALIDATION_ROW"):
                permissive_validate(rows)

    def test_valid_quantity_metrics_use_full_sample(self):
        rows=[
            {"event_start_ts":"2026-01-01T12:00:00+00:00","model_probability":0.2,"outcome":0,"quantity_prediction":10.0,"quantity_actual":12.0},
            {"event_start_ts":"2026-01-02T12:00:00+00:00","model_probability":0.8,"outcome":1,"quantity_prediction":20.0,"quantity_actual":18.0},
        ]
        result=permissive_validate(rows)
        self.assertEqual(result.mae,2.0)
        self.assertEqual(result.rmse,2.0)
        self.assertTrue(math.isfinite(result.mae))
        self.assertTrue(math.isfinite(result.rmse))


if __name__=="__main__":
    unittest.main()
