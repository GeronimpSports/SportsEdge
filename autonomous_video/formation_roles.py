from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from math import hypot
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


@dataclass
class RoleDetection:
    role: str
    team: str
    x: float
    y: float
    box: tuple[float, float, float, float]
    confidence: float
    geometry_confidence: float

    def to_dict(self):
        return asdict(self)


def _torso_colors(frame, box):
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    xa, xb = x1 + int(.2 * bw), x2 - int(.2 * bw)
    ya, yb = y1 + int(.05 * bh), y1 + int(.70 * bh)
    crop = frame[max(0, ya):min(frame.shape[0], yb), max(0, xa):min(frame.shape[1], xb)]
    if crop.size == 0:
        return 0.0, 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    yellow = ((hsv[:, :, 0] >= 20) & (hsv[:, :, 0] <= 42) &
              (hsv[:, :, 1] >= 80) & (hsv[:, :, 2] >= 80)).mean()
    white = ((hsv[:, :, 1] <= 70) & (hsv[:, :, 2] >= 140)).mean()
    return float(yellow), float(white)


def _dedupe(rows, distance=11.0):
    kept = []
    for row in sorted(rows, key=lambda r: r['confidence'] * max(r['yellow'], r['white'], .1), reverse=True):
        if all(hypot(row['x'] - q['x'], row['y'] - q['y']) > distance for q in kept):
            kept.append(row)
    return kept


def _collect_people(frame, model):
    h, w = frame.shape[:2]
    result = model.predict(frame, classes=[0], conf=.05, imgsz=1280, verbose=False)[0]
    rows = []
    for b in result.boxes:
        box = tuple(float(v) for v in b.xyxy[0].cpu().numpy())
        x1, y1, x2, y2 = box
        x, y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        bh = y2 - y1
        if not (.12 * h < y < .80 * h and 22 < bh < 170 and .03 * w < x < .97 * w):
            continue
        yellow, white = _torso_colors(frame, box)
        rows.append({
            'x': x, 'y': y, 'box': box,
            'confidence': float(b.conf[0].cpu()),
            'yellow': yellow, 'white': white,
        })
    return rows


def _best_ol_group(offense):
    best = None
    for a, b in combinations(offense, 2):
        va = np.array([a['x'], a['y']]); vb = np.array([b['x'], b['y']])
        vec = vb - va; norm = float(np.linalg.norm(vec))
        if norm < 25:
            continue
        u = vec / norm
        aligned = []
        for p in offense:
            rel = np.array([p['x'], p['y']]) - va
            distance = abs(u[0] * rel[1] - u[1] * rel[0])
            if distance < 14:
                aligned.append((float(np.dot(rel, u)), p, distance))
        aligned.sort(key=lambda z: z[0])
        for i in range(len(aligned) - 4):
            group = aligned[i:i + 5]
            span = group[-1][0] - group[0][0]
            if not 35 < span < 125:
                continue
            gaps = [group[j + 1][0] - group[j][0] for j in range(4)]
            max_gap = max(gaps)
            residual = sum(z[2] for z in group)
            score = 500 - 1.5 * span - 2.0 * max_gap - 2.0 * residual
            score += 10 * sum(z[1]['confidence'] for z in group)
            if best is None or score > best[0]:
                best = (score, [z[1] for z in group])
    if best is None:
        raise RuntimeError('could not identify a five-man offensive line')
    return best[1]


def classify_formation(frame, model_path='yolo11x.pt'):
    model = YOLO(model_path)
    people = _collect_people(frame, model)
    offense = _dedupe([p for p in people if p['yellow'] > .60 and p['yellow'] > 1.3 * p['white']])
    ol = _best_ol_group(offense)
    ol_ids = {id(p) for p in ol}
    points = np.array([[p['x'], p['y']] for p in ol])
    center = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
    u = vt[0]
    normal = np.array([-u[1], u[0]])
    latitudes = [float(np.dot(np.array([p['x'], p['y']]) - center, u)) for p in ol]
    ol_half = max(abs(min(latitudes)), abs(max(latitudes)))
    ordered_ol = sorted(latitudes)
    spacing = float(np.median(np.diff(ordered_ol))) if len(ordered_ol) > 1 else 18.0
    spacing = max(12.0, min(30.0, spacing))

    defense = _dedupe([p for p in people if p['white'] > .34 and p['yellow'] < .40], distance=16.0)
    if defense:
        nearby = sorted(defense, key=lambda p: abs(float(np.dot(np.array([p['x'], p['y']]) - center, normal))))[:8]
        median_projection = float(np.median([
            float(np.dot(np.array([p['x'], p['y']]) - center, normal)) for p in nearby
        ]))
        defense_sign = 1.0 if median_projection > 0 else -1.0
    else:
        defense_sign = 1.0

    roles = []
    for p in ol:
        roles.append(RoleDetection('OL', 'offense', p['x'], p['y'], p['box'], p['confidence'], .95))

    for p in offense:
        if id(p) in ol_ids:
            continue
        rel = np.array([p['x'], p['y']]) - center
        line_distance = abs(float(normal @ rel))
        lateral = abs(float(u @ rel))
        if line_distance < 1.2 * spacing and lateral < ol_half + 2.0 * spacing:
            continue
        roles.append(RoleDetection('ELIGIBLE', 'offense', p['x'], p['y'], p['box'], p['confidence'], .80))

    for p in defense:
        rel = np.array([p['x'], p['y']]) - center
        lateral = float(u @ rel)
        depth = defense_sign * float(normal @ rel)
        if depth <= .8 * spacing:
            continue
        if depth < 4.5 * spacing and abs(lateral) < ol_half + 5.0 * spacing:
            role, gc = 'DL', .88
        elif depth < 9.0 * spacing and abs(lateral) < ol_half + 7.0 * spacing:
            role, gc = 'LB', .82
        elif depth >= 10.0 * spacing and abs(lateral) < ol_half + 8.0 * spacing:
            role, gc = 'SAFETY', .78
        else:
            role, gc = 'DB', .72
        roles.append(RoleDetection(role, 'defense', p['x'], p['y'], p['box'], p['confidence'], gc))

    return {
        'roles': [r.to_dict() for r in roles],
        'formation': {
            'los_center': [float(center[0]), float(center[1])],
            'los_direction': [float(u[0]), float(u[1])],
            'defense_normal': [float(defense_sign * normal[0]), float(defense_sign * normal[1])],
            'ol_spacing_px': spacing,
        },
    }


def classify_video_frame(video: str | Path, time_sec: float, model_path='yolo11x.pt'):
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, float(time_sec) * 1000.0)
    ok, frame = cap.read(); cap.release()
    if not ok:
        raise RuntimeError('could not read formation frame')
    result = classify_formation(frame, model_path=model_path)
    result['time_sec'] = float(time_sec)
    return result
