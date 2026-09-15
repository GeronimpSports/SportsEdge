from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot, log
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

try:
    from .player_detector import PlayerDetection, detect_players, select_quarterback
except ImportError:
    from player_detector import PlayerDetection, detect_players, select_quarterback


@dataclass
class TrackedFrame:
    time_sec: float
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    visible: bool
    confidence: float
    status: str

    def to_dict(self):
        return asdict(self)


def _team_score(frame: np.ndarray, box: tuple[float, float, float, float]) -> float:
    x, y, w, h = [int(v) for v in box]
    height, width = frame.shape[:2]
    crop = frame[max(0, y):min(height, y + h), max(0, x):min(width, x + w)]
    if crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([20, 75, 75]), np.array([42, 255, 255]))
    return float(mask.mean() / 255.0)


def _box_from_detection(detection: PlayerDetection) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = detection.box
    return (float(x1), float(y1), float(x2 - x1), float(y2 - y1))


def _center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def track_qb_hybrid(
    video: str | Path,
    snap_sec: float,
    *,
    seconds_before: float = 1.0,
    seconds_after: float = 3.2,
    detector_interval: float = 0.20,
    model_path: str = "yolo11n.pt",
) -> dict:
    video = str(video)
    model = YOLO(model_path)
    cap = cv2.VideoCapture(video)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    start = max(0.0, snap_sec - seconds_before)
    end = snap_sec + seconds_after
    select_t = max(start, snap_sec - 0.7)

    cap.set(cv2.CAP_PROP_POS_MSEC, select_t * 1000)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError("could not read player-selection frame")

    qb = select_quarterback(detect_players(model, frame), frame.shape)
    box = _box_from_detection(qb)
    tracker = cv2.TrackerCSRT_create()
    tracker.init(frame, tuple(map(int, box)))

    team_floor = max(0.14, min(0.28, qb.team_score * 0.55))
    last_anchor = _center(box)
    prev_anchor = last_anchor
    last_area = box[2] * box[3]
    last_detector_t = select_t
    out = [TrackedFrame(select_t, *last_anchor, box[2], box[3], True, 1.0, "INITIAL_LOCK")]

    cap.set(cv2.CAP_PROP_POS_MSEC, (select_t + 1 / fps) * 1000)
    frame_no = int((select_t + 1 / fps) * fps)
    misses = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_no / fps
        frame_no += 1
        if t > end:
            break

        ok_track, tracked_box = tracker.update(frame)
        if ok_track:
            tracked_box = tuple(float(v) for v in tracked_box)
            track_center = _center(tracked_box)
            track_team = _team_score(frame, tracked_box)
        else:
            tracked_box = None
            track_center = None
            track_team = 0.0

        anchored = False
        chosen = None
        if t - last_detector_t >= detector_interval - 1e-4 or not ok_track or track_team < team_floor:
            rows = detect_players(model, frame)
            last_detector_t = t
            vx = last_anchor[0] - prev_anchor[0]
            vy = last_anchor[1] - prev_anchor[1]
            predicted = (last_anchor[0] + vx, last_anchor[1] + vy)
            candidates = [d for d in rows if d.team_score >= team_floor * 0.75]
            scored = []
            for detection in candidates:
                cx, cy = detection.center
                distance = hypot(cx - predicted[0], cy - predicted[1])
                size_penalty = abs(log(max(detection.area, 1.0) / max(last_area, 1.0)))
                color_penalty = max(0.0, team_floor - detection.team_score)
                cost = distance + 28.0 * size_penalty + 100.0 * color_penalty
                if distance <= 145.0 + 30.0 * min(misses, 2):
                    scored.append((cost, detection))

            if scored:
                chosen = min(scored, key=lambda item: item[0])[1]
                box = _box_from_detection(chosen)
                if chosen.team_score >= team_floor * 0.75:
                    prev_anchor = last_anchor
                    last_anchor = chosen.center
                    last_area = chosen.area
                    misses = 0
                    anchored = True
                    tracker = cv2.TrackerCSRT_create()
                    tracker.init(frame, tuple(map(int, box)))
            if not anchored:
                misses += 1

        if anchored:
            x, y = last_anchor
            out.append(
                TrackedFrame(t, x, y, box[2], box[3], True, min(1.0, 0.55 + chosen.team_score), "DETECTOR_ANCHOR")
            )
        elif (
            ok_track
            and track_team >= team_floor
            and hypot(track_center[0] - last_anchor[0], track_center[1] - last_anchor[1]) < 115.0
        ):
            x, y = track_center
            out.append(
                TrackedFrame(t, x, y, tracked_box[2], tracked_box[3], True, min(0.85, 0.35 + track_team), "VISUAL_TRACK")
            )
        else:
            out.append(TrackedFrame(t, None, None, None, None, False, 0.0, "OCCLUDED_HIDE"))

        if misses > 6 and sum(1 for point in out[-10:] if point.visible) == 0:
            break

    cap.release()
    return {
        "role": "quarterback",
        "snap_sec": snap_sec,
        "team_floor": team_floor,
        "points": [point.to_dict() for point in out],
    }
