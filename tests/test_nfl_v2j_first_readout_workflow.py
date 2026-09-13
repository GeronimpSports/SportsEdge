from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
WF=ROOT/'.github/workflows/nfl-v2j-first-readout.yml'

class NFLV2JFirstReadoutWorkflowTests(unittest.TestCase):
    def test_readout_only_executes_on_trusted_main_push(self):
        text=WF.read_text(encoding='utf-8')
        self.assertIn("if: github.event_name == 'push' && github.ref == 'refs/heads/main'", text)
        self.assertIn('Run preregistered V2J first historical readout', text)
        self.assertIn('--max-abs-error=0.005', text.replace(' ','')) if '--max-abs-error' in text else self.assertIn('max_abs_error=0.005', text)
    def test_zero_authority_and_no_engine_are_enforced(self):
        text=WF.read_text(encoding='utf-8')
        self.assertIn('post_readout_retuning_allowed', text)
        self.assertIn('production_registry_consumes_this_artifact', text)
        self.assertIn("e.get('nfl_props')!='NO_ENGINE'", text)
        self.assertNotIn('stake_units', text)

if __name__=='__main__': unittest.main()
