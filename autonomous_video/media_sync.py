from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class SyncResult:
    reference_snap_sec: float
    secondary_snap_sec: float
    secondary_offset_sec: float
    confidence: float

    def to_dict(self):
        return asdict(self)


def _motion_series(path: str | Path, fps: int = 10, width: int = 160, height: int = 90) -> np.ndarray:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", f"fps={fps},scale={width}:{height},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
    ]
    raw = subprocess.check_output(cmd)
    frame_size = width * height
    count = len(raw) // frame_size
    if count < 8:
        raise ValueError(f"not enough frames in {path}")
    frames = np.frombuffer(raw[: count * frame_size], dtype=np.uint8).reshape(count, height, width)
    diffs = np.mean(np.abs(np.diff(frames.astype(np.int16), axis=0)), axis=(1, 2)) / 255.0
    return diffs


def detect_snap(path: str | Path, fps: int = 10) -> tuple[float, float]:
    """Self-calibrating snap detector.

    Learns each clip's own motion scale so distant wide cameras are not held to
    the same absolute-motion threshold as tight/end-zone cameras. A snap must
    produce sustained motion, which rejects one-frame camera cuts.
    """
    motion = _motion_series(path, fps=fps)
    pre = max(8, int(1.2 * fps))
    post = max(10, int(1.5 * fps))
    p25 = float(np.percentile(motion, 25))
    p90 = float(np.percentile(motion, 90))
    dynamic_floor = max(0.008, min(0.028, p25 + 0.18 * (p90 - p25)))
    candidates = []
    for i in range(pre, len(motion) - post):
        before = float(np.mean(motion[i-pre:i]))
        after = motion[i:i+post]
        after_mean = float(np.mean(after))
        active = max(dynamic_floor, before * 2.2)
        sustained = float(np.mean(after > active))
        ratio = after_mean / max(before, 0.0025)
        if after_mean >= dynamic_floor * 1.35 and ratio >= 1.65 and sustained >= 0.52:
            score = ratio * sustained * after_mean
            candidates.append((i, score, ratio, sustained))
    if not candidates:
        raise RuntimeError(f"could not find a sustained-motion snap in {path}")
    i, score, ratio, sustained = candidates[0]
    confidence = min(0.99, 0.42 + min(ratio, 6.0) * 0.065 + sustained * 0.22)
    return round((i + 1) / fps, 2), round(confidence, 3)


def sync_pair(reference: str | Path, secondary: str | Path, fps: int = 10) -> SyncResult:
    ref_snap, ref_conf = detect_snap(reference, fps=fps)
    sec_snap, sec_conf = detect_snap(secondary, fps=fps)
    return SyncResult(
        reference_snap_sec=ref_snap,
        secondary_snap_sec=sec_snap,
        secondary_offset_sec=round(ref_snap - sec_snap, 2),
        confidence=round(min(ref_conf, sec_conf), 3),
    )


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("secondary")
    args = parser.parse_args()
    print(json.dumps(sync_pair(args.reference, args.secondary).to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
