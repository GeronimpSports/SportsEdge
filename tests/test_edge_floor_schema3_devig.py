from copy import deepcopy
import unittest

from sportsedge.edge_floors import (
    EdgeFloorError,
    load_edge_floor_config,
    require_frozen_devig_policy,
)


class EdgeFloorSchema3DevigTests(unittest.TestCase):
    def test_current_schema3_registry_resolves_frozen_devig_policy(self):
        config = load_edge_floor_config()
        self.assertEqual(config["truth_gate"]["schema_version"], 3)
        policy = require_frozen_devig_policy(config=config)
        self.assertEqual(policy.policy_id, "EDGE_FLOOR_DEVIG_V1")
        self.assertEqual(policy.sensitivity_failure, "BLOCK")

    def test_unknown_future_schema_still_fails_closed(self):
        config = deepcopy(load_edge_floor_config())
        config["truth_gate"]["schema_version"] = 4
        with self.assertRaisesRegex(EdgeFloorError, "EDGE_FLOOR_SCHEMA_VERSION_MISMATCH"):
            require_frozen_devig_policy(config=config)


if __name__ == "__main__":
    unittest.main()
