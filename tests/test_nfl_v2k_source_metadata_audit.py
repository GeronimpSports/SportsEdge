import json
from pathlib import Path
import unittest


AUDIT = Path("sportsedge/sports/nfl/NFL_V2K_SOURCE_METADATA_AUDIT_2026-09-13.json")
REGISTRY = Path("sportsedge/sports/nfl/NFL_V2K_SOURCE_ASSET_REGISTRY_2026-09-13.json")


class NFLV2KSourceMetadataAuditTests(unittest.TestCase):
    def test_provider_metadata_gap_matches_registry_unresolved_seasons(self):
        audit = json.loads(AUDIT.read_text())
        registry = json.loads(REGISTRY.read_text())
        seasons = [row["season"] for row in audit["assets"]]
        self.assertEqual(seasons, registry["unresolved_seasons"])
        self.assertEqual(seasons, list(range(2010, 2019)))
        self.assertTrue(all(row["state"] == "uploaded" for row in audit["assets"]))
        self.assertTrue(all(row["digest"] is None for row in audit["assets"]))
        self.assertTrue(all(row["size_bytes"] > 0 for row in audit["assets"]))
        self.assertEqual(audit["required_next_evidence"], "DIRECT_DOWNLOADED_BYTE_SHA256")
        self.assertFalse(audit["source_manifest_complete"])

    def test_metadata_audit_carries_no_model_or_betting_authority(self):
        audit = json.loads(AUDIT.read_text())
        self.assertFalse(audit["readout_consumed"])
        for key in ("model_p_authority", "promotion_authority", "truth_gate_authority", "official_authority"):
            self.assertFalse(audit[key], key)


if __name__ == "__main__":
    unittest.main()
