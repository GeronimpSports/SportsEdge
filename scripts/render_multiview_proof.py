from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "autonomous_video"))
from narration import synthesize_prototype_narration
from proof_renderer import render_proof

parser = argparse.ArgumentParser()
parser.add_argument("--wide", required=True)
parser.add_argument("--end-zone", required=True)
parser.add_argument("--narration")
parser.add_argument("--narration-text")
parser.add_argument("--output", required=True)
args = parser.parse_args()

narration = args.narration
if args.narration_text:
    narration = str(Path(args.output).with_suffix(".narration.mp3"))
    synthesize_prototype_narration(args.narration_text, narration)

print(render_proof(args.wide, args.end_zone, args.output, narration))
