from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "autonomous_video"))

from player_aware_telestration import render_qb_tracking


parser = argparse.ArgumentParser()
parser.add_argument("--video", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--snap", type=float, required=True)
args = parser.parse_args()

result = render_qb_tracking(args.video, args.output, args.snap)
print(json.dumps({key: value for key, value in result.items() if key != "track"}, indent=2))
