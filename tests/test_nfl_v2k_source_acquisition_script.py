import hashlib
import io
import unittest

from scripts.acquire_nfl_v2k_source_assets import parse_seasons, sha256_stream


class NFLV2KSourceAcquisitionScriptTests(unittest.TestCase):
    def test_stream_hash_matches_exact_bytes_and_sink(self):
        raw = (b"sportsedge-v2k-source" * 1000) + b"\x00\xff"
        sink = io.BytesIO()
        digest, byte_count = sha256_stream(io.BytesIO(raw), sink=sink)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertEqual(byte_count, len(raw))
        self.assertEqual(sink.getvalue(), raw)

    def test_default_unresolved_era_can_be_parsed_deterministically(self):
        self.assertEqual(parse_seasons("2018,2010,2018,2011"), (2010, 2011, 2018))

    def test_outside_preregistered_window_fails_closed(self):
        for raw in ("2009", "2026", ""):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_seasons(raw)


if __name__ == "__main__":
    unittest.main()
