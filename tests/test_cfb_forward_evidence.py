import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sportsedge.sports.cfb.forward_evidence import audit_cfb_forward_market_weather_evidence


class CFBForwardEvidenceTests(unittest.TestCase):
    def _raw(self, root: Path, rel: str, payload) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return hashlib.sha256(body).hexdigest()

    def _market_rows(self, root: Path):
        decision_rel = "archive/closing-lines/raw/americanfootball_ncaaf/decision.json"
        close_rel = "archive/closing-lines/raw/americanfootball_ncaaf/close.json"
        decision_sha = self._raw(root, decision_rel, [{"capture": "decision"}])
        close_sha = self._raw(root, close_rel, [{"capture": "close"}])
        common = {
            "sport_key": "americanfootball_ncaaf",
            "evidence_class": "NOT_EVIDENCE",
            "promotion_authority": False,
            "event_id": "event-1",
            "home_team": "Home State",
            "away_team": "Away Tech",
            "book": "draftkings",
            "market": "spreads",
            "commence_time": "2026-09-19T00:00:00Z",
            "sides_in_market": 2,
            "raw_payload_preserved": True,
        }
        rows = []
        for outcome, point, price in (("Home State", -3.0, -110), ("Away Tech", 3.0, -110)):
            rows.append({
                **common,
                "window": "decision",
                "capture_id": "decision-cap",
                "captured_at": "2026-09-18T23:00:00Z",
                "outcome": outcome,
                "point": point,
                "price_american": price,
                "fetch_sha256": decision_sha,
                "fetch_payload_sha256": decision_sha,
                "fetch_payload_path": decision_rel,
            })
        for outcome, point, price in (("Home State", -3.5, -108), ("Away Tech", 3.5, -112)):
            rows.append({
                **common,
                "window": "close",
                "capture_id": "close-cap",
                "captured_at": "2026-09-18T23:55:00Z",
                "outcome": outcome,
                "point": point,
                "price_american": price,
                "fetch_sha256": close_sha,
                "fetch_payload_sha256": close_sha,
                "fetch_payload_path": close_rel,
            })
        return rows

    def _weather_rows(self, root: Path):
        rel = "history/cfb/weather/raw/weather.json"
        sha = self._raw(root, rel, {"weather": {"temperature": 72}})
        return [{
            "schema_version": "CFB_PIT_WEATHER_OBSERVATION_V1",
            "sport": "CFB",
            "promotion_authority": False,
            "model_p_created": False,
            "source": "ESPN_CFB_SUMMARY",
            "raw_relative_path": rel,
            "raw_sha256": sha,
            "observation_id": "weather-1",
            "home_team": "Home State",
            "away_team": "Away Tech",
            "commence_time": "2026-09-19T00:00:00Z",
            "captured_at_utc": "2026-09-18T23:45:00Z",
            "status_state": "pre",
            "weather": {"temperature": 72},
        }]

    def test_valid_pair_and_weather_are_admitted_without_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = audit_cfb_forward_market_weather_evidence(
                self._market_rows(root), self._weather_rows(root), data_root=root
            )
            self.assertTrue(report["market_weather_evidence_ready"])
            self.assertEqual(report["admitted_unit_count"], 1)
            self.assertFalse(report["truth_gate_ready"])
            self.assertFalse(report["promotion_authority"])
            self.assertFalse(report["model_p_created"])

    def test_missing_close_stays_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = [r for r in self._market_rows(root) if r["window"] == "decision"]
            report = audit_cfb_forward_market_weather_evidence(rows, self._weather_rows(root), data_root=root)
            self.assertFalse(report["market_weather_evidence_ready"])
            self.assertIn("PAIRED_MARKET_EVIDENCE_MISSING", report["blockers"])

    def test_tampered_raw_market_payload_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = self._market_rows(root)
            (root / rows[0]["fetch_payload_path"]).write_bytes(b"tampered")
            report = audit_cfb_forward_market_weather_evidence(rows, self._weather_rows(root), data_root=root)
            self.assertFalse(report["market_weather_evidence_ready"])
            self.assertIn("MARKET_EVIDENCE_BINDING_ERRORS", report["blockers"])


if __name__ == "__main__":
    unittest.main()
