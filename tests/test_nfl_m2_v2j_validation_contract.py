import unittest
from sportsedge.sports.nfl import m2_v2j_validation as v

class NFLV2JValidationContractTests(unittest.TestCase):
    def test_contract_constants(self):
        self.assertEqual(v._KEYS,(-7,-3,3,7))
    def test_empty_inputs_fail_closed(self):
        with self.assertRaises(Exception):
            v.build_nfl_m2_v2j_candidate_evidence([],[],source_manifest_sha256='0'*64)

if __name__=='__main__': unittest.main()
