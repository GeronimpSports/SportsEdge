from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'autonomous_video'))

from temporal_formation import analyze_tight_formation

parser = argparse.ArgumentParser(description='Game-agnostic tight-angle formation analysis')
parser.add_argument('video')
parser.add_argument('--snap', type=float, help='Optional snap timestamp; auto-detected when omitted')
parser.add_argument('--model', default='yolo11x.pt')
args = parser.parse_args()

result = analyze_tight_formation(args.video, snap_sec=args.snap, model_path=args.model)
print(json.dumps(result, indent=2))
