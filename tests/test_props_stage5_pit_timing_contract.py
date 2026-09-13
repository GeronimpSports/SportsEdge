import unittest

from sportsedge.props_pit_stage5 import validate_pit_inputs


def nfl_payload(**overrides):
    payload={
        "asof_ts":"2026-09-13T12:00:00-05:00",
        "event_start_ts":"2026-09-13T13:00:00-05:00",
        "source_id":"source",
        "entity_id":"player",
        "availability_status":"ACTIVE",
        "snap_share":0.8,
        "role_share":0.5,
        "depth_status":"STARTER",
        "qb_status":"STARTER_CONFIRMED",
        "weather_status":"KNOWN",
        "opponent_feature_asof_ts":"2026-09-13T17:00:00+00:00",
    }
    payload.update(overrides)
    return payload


class PropsStage5PitTimingContractTests(unittest.TestCase):
    def test_valid_offsets_compare_as_absolute_instants(self):
        result=validate_pit_inputs("NFL",nfl_payload())
        self.assertTrue(result["pit_validated"])

    def test_prediction_must_be_strictly_before_event(self):
        with self.assertRaisesRegex(ValueError,"PIT_NOT_STRICTLY_BEFORE_EVENT_START"):
            validate_pit_inputs("NFL",nfl_payload(asof_ts="2026-09-13T13:00:00-05:00"))
        with self.assertRaisesRegex(ValueError,"PIT_NOT_STRICTLY_BEFORE_EVENT_START"):
            validate_pit_inputs("NFL",nfl_payload(asof_ts="2026-09-13T13:01:00-05:00"))

    def test_opponent_feature_must_exist_by_decision_time(self):
        with self.assertRaisesRegex(ValueError,"OPPONENT_FEATURE_AFTER_DECISION_ASOF"):
            validate_pit_inputs("NFL",nfl_payload(opponent_feature_asof_ts="2026-09-13T17:00:01+00:00"))

    def test_timezone_naive_timestamps_fail_closed(self):
        cases={
            "asof_ts":"2026-09-13T12:00:00",
            "event_start_ts":"2026-09-13T13:00:00",
            "opponent_feature_asof_ts":"2026-09-13T11:00:00",
        }
        for field,value in cases.items():
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,f"PIT_TIMESTAMP_MUST_BE_TIMEZONE_AWARE:{field}"):
                validate_pit_inputs("NFL",nfl_payload(**{field:value}))

    def test_malformed_timestamp_fails_with_explicit_reason(self):
        with self.assertRaisesRegex(ValueError,"PIT_TIMESTAMP_INVALID:asof_ts"):
            validate_pit_inputs("NFL",nfl_payload(asof_ts="not-a-time"))


if __name__=="__main__":
    unittest.main()
