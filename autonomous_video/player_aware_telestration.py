from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

import cv2

try:
    from .hybrid_player_tracker import track_qb_hybrid
except ImportError:
    from hybrid_player_tracker import track_qb_hybrid


def _nearest(points: list[dict], t: float) -> dict:
    return min(points, key=lambda point: abs(point["time_sec"] - t))


def render_qb_tracking(
    video: str | Path,
    output: str | Path,
    snap_sec: float,
    *,
    seconds_before: float = 0.8,
    seconds_after: float = 3.0,
) -> dict:
    video = str(video)
    output = str(output)
    track = track_qb_hybrid(video, snap_sec, seconds_before=seconds_before, seconds_after=seconds_after)
    points = track["points"]
    start = max(0.0, snap_sec - seconds_before)
    end = snap_sec + seconds_after

    cap = cv2.VideoCapture(video)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)

    with tempfile.TemporaryDirectory(prefix="qb_track_") as tmp_dir:
        raw_output = str(Path(tmp_dir) / "raw.mp4")
        writer = cv2.VideoWriter(raw_output, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        frame_idx = 0
        smooth = None
        trail: list[tuple[int, int]] = []
        drawn = 0
        hidden = 0

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = start + frame_idx / fps
            frame_idx += 1
            if t > end:
                break

            point = _nearest(points, t)
            if abs(point["time_sec"] - t) <= 0.12 and point["visible"] and point["x"] is not None:
                target = (float(point["x"]), float(point["y"]))
                if smooth is None:
                    smooth = target
                else:
                    smooth = (
                        0.45 * target[0] + 0.55 * smooth[0],
                        0.45 * target[1] + 0.55 * smooth[1],
                    )
                cx, cy = int(smooth[0]), int(smooth[1])
                radius = max(34, int(max(point["width"], point["height"]) * 0.34))
                trail.append((cx, cy))
                trail = trail[-18:]

                for index in range(1, len(trail)):
                    alpha = index / max(1, len(trail) - 1)
                    thickness = max(1, int(4 * alpha))
                    cv2.line(frame, trail[index - 1], trail[index], (0, 210, 255), thickness, cv2.LINE_AA)

                cv2.circle(frame, (cx, cy), radius, (0, 235, 255), 5, cv2.LINE_AA)
                tip = (cx, max(10, cy - radius))
                tail = (max(40, cx - 95), max(35, cy - radius - 75))
                cv2.arrowedLine(frame, tail, tip, (0, 235, 255), 5, cv2.LINE_AA, tipLength=0.18)
                cv2.rectangle(frame, (24, 22), (390, 82), (0, 0, 0), -1)
                cv2.putText(
                    frame,
                    "AUTO TRACK: QB",
                    (43, 62),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.05,
                    (0, 235, 255),
                    3,
                    cv2.LINE_AA,
                )
                drawn += 1
            else:
                cv2.rectangle(frame, (24, 22), (455, 82), (0, 0, 0), -1)
                cv2.putText(
                    frame,
                    "TRACK HIDDEN: UNCERTAIN",
                    (42, 61),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.78,
                    (0, 235, 255),
                    2,
                    cv2.LINE_AA,
                )
                hidden += 1

            writer.write(frame)

        writer.release()
        cap.release()
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                raw_output,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "19",
                "-pix_fmt",
                "yuv420p",
                "-an",
                output,
            ],
            check=True,
        )

    return {
        "output": output,
        "role": "quarterback",
        "drawn_frames": drawn,
        "hidden_frames": hidden,
        "track": track,
    }
