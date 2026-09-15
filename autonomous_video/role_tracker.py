from __future__ import annotations

from dataclasses import asdict, dataclass
from math import hypot, log
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

try:
    from .formation_roles import classify_video_frame, _collect_people
except ImportError:
    from formation_roles import classify_video_frame, _collect_people


@dataclass
class RoleTrackPoint:
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


def _color_scores(frame, box):
    x, y, w, h = [int(v) for v in box]
    H, W = frame.shape[:2]
    x1 = max(0, x + int(.18 * w)); x2 = min(W, x + int(.82 * w))
    y1 = max(0, y + int(.05 * h)); y2 = min(H, y + int(.68 * h))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, np.array([20, 80, 80]), np.array([42, 255, 255])).mean() / 255.0
    white = cv2.inRange(hsv, np.array([0, 0, 140]), np.array([179, 70, 255])).mean() / 255.0
    return float(yellow), float(white)


def _team_score(frame, box, team):
    yellow, white = _color_scores(frame, box)
    return yellow if team == 'offense' else white


def _box4(box):
    x1, y1, x2, y2 = box
    return (float(x1), float(y1), float(x2 - x1), float(y2 - y1))


def _center(box):
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def _pick_role(role_map, role):
    rows = [r for r in role_map['roles'] if r['role'] == role]
    if not rows:
        raise RuntimeError(f'no {role} found in role map')
    return max(rows, key=lambda r: r['confidence'] * r['geometry_confidence'])


def track_role(video: str | Path, role_time: float, role: str, *, seconds_after=4.0,
               detector_interval=.18, model_path='yolo11x.pt') -> dict:
    video = str(video)
    role_map = classify_video_frame(video, role_time, model_path=model_path)
    target = _pick_role(role_map, role)
    team = target['team']
    box = _box4(target['box'])

    model = YOLO(model_path)
    cap = cv2.VideoCapture(video)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.set(cv2.CAP_PROP_POS_MSEC, role_time * 1000.0)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError('could not read role frame')

    tracker = cv2.TrackerCSRT_create()
    tracker.init(frame, tuple(map(int, box)))
    initial_color = _team_score(frame, box, team)
    color_floor = max(.12, min(.32, initial_color * .50))
    last_anchor = _center(box)
    prev_anchor = last_anchor
    last_anchor_t = role_time
    prev_anchor_t = role_time
    last_area = box[2] * box[3]
    last_detector_t = role_time
    points = [RoleTrackPoint(role_time, *last_anchor, box[2], box[3], True, 1.0, 'ROLE_LOCK')]

    frame_no = int(role_time * fps) + 1
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
    misses = 0
    end = role_time + seconds_after
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_no / fps
        frame_no += 1
        if t > end:
            break

        ok_track, raw_box = tracker.update(frame)
        if ok_track:
            track_box = tuple(float(v) for v in raw_box)
            track_center = _center(track_box)
            track_yellow, track_white = _color_scores(frame, track_box)
            track_color = track_yellow if team == 'offense' else track_white
        else:
            track_box = None
            track_center = None
            track_color = 0.0
            track_yellow = 0.0
            track_white = 0.0

        anchored = False
        chosen = None
        if t - last_detector_t >= detector_interval - 1e-4 or not ok_track or track_color < color_floor:
            detections = _collect_people(frame, model)
            last_detector_t = t
            history_dt = max(last_anchor_t - prev_anchor_t, 1.0 / fps)
            vx = (last_anchor[0] - prev_anchor[0]) / history_dt
            vy = (last_anchor[1] - prev_anchor[1]) / history_dt
            speed = hypot(vx, vy)
            if speed > 450:
                scale = 450 / speed
                vx *= scale; vy *= scale
            forward_dt = max(t - last_anchor_t, 1.0 / fps)
            predicted = (last_anchor[0] + vx * forward_dt, last_anchor[1] + vy * forward_dt)
            scored = []
            for d in detections:
                team_score = d['yellow'] if team == 'offense' else d['white']
                if team == 'defense' and d['yellow'] >= .45:
                    continue
                if team_score < color_floor * .75:
                    continue
                center = (d['x'], d['y'])
                distance = hypot(center[0] - predicted[0], center[1] - predicted[1])
                area = max(1.0, (d['box'][2] - d['box'][0]) * (d['box'][3] - d['box'][1]))
                size_penalty = abs(log(area / max(last_area, 1.0)))
                cost = distance + 25.0 * size_penalty + 70.0 * max(0.0, color_floor - team_score)
                max_distance = 45 + 160 * forward_dt + 20 * min(misses, 3)
                implied_speed = hypot(center[0] - last_anchor[0], center[1] - last_anchor[1]) / forward_dt
                if distance <= max_distance and implied_speed <= 500:
                    scored.append((cost, d, team_score))
            if scored:
                _, chosen, team_score = min(scored, key=lambda z: z[0])
                box = _box4(chosen['box'])
                prev_anchor = last_anchor
                prev_anchor_t = last_anchor_t
                last_anchor = (chosen['x'], chosen['y'])
                last_anchor_t = t
                last_area = box[2] * box[3]
                tracker = cv2.TrackerCSRT_create()
                tracker.init(frame, tuple(map(int, box)))
                misses = 0
                anchored = True
            else:
                misses += 1
        if anchored:
            x, y = last_anchor
            points.append(RoleTrackPoint(t, x, y, box[2], box[3], True,
                                         min(1.0, .55 + team_score), 'DETECTOR_REID'))
        elif ok_track and track_color >= color_floor and (team == 'offense' or track_yellow < .32) and hypot(track_center[0] - last_anchor[0], track_center[1] - last_anchor[1]) < 95:
            x, y = track_center
            prev_anchor = last_anchor
            prev_anchor_t = last_anchor_t
            last_anchor = track_center
            last_anchor_t = t
            points.append(RoleTrackPoint(t, x, y, track_box[2], track_box[3], True,
                                         min(.85, .35 + track_color), 'VISUAL_TRACK'))
        else:
            points.append(RoleTrackPoint(t, None, None, None, None, False, 0.0, 'OCCLUDED_HIDE'))

        if misses > 7 and sum(1 for p in points[-12:] if p.visible) == 0:
            break

    cap.release()
    return {
        'role': role,
        'team': team,
        'role_time': role_time,
        'color_floor': color_floor,
        'initial_target': target,
        'points': [p.to_dict() for p in points],
    }
