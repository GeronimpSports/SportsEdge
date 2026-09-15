from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np
from ultralytics import YOLO


@dataclass
class PlayerDetection:
    box: tuple[float, float, float, float]
    confidence: float
    team_score: float

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(1.0, (x2 - x1) * (y2 - y1))


def _yellow_score(frame: np.ndarray, box: tuple[float, float, float, float]) -> float:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([20, 75, 75]), np.array([42, 255, 255]))
    return float(mask.mean() / 255.0)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    ua = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    ub = max(1.0, (bx2 - bx1) * (by2 - by1))
    return inter / max(1.0, ua + ub - inter)


def _dedupe(rows: Iterable[PlayerDetection]) -> list[PlayerDetection]:
    kept: list[PlayerDetection] = []
    for row in sorted(rows, key=lambda d: d.confidence, reverse=True):
        if all(_iou(row.box, existing.box) < 0.60 for existing in kept):
            kept.append(row)
    return kept


def detect_players(model: YOLO, frame: np.ndarray, imgsz: int = 960) -> list[PlayerDetection]:
    result = model.predict(frame, classes=[0], conf=0.06, imgsz=imgsz, verbose=False)[0]
    rows = []
    for box in result.boxes:
        xyxy = tuple(float(v) for v in box.xyxy[0].cpu().numpy())
        rows.append(PlayerDetection(xyxy, float(box.conf[0].cpu()), _yellow_score(frame, xyxy)))
    return _dedupe(rows)


def select_quarterback(rows: list[PlayerDetection], shape: tuple[int, int, int]) -> PlayerDetection:
    h, w = shape[:2]
    offense = [d for d in rows if d.team_score >= 0.10 and 0.12 * w < d.center[0] < 0.90 * w]
    line = [d for d in offense if d.center[1] >= 0.44 * h]
    if len(line) < 3:
        raise RuntimeError("not enough offensive players to estimate line of scrimmage")
    los_y = float(np.median([d.center[1] for d in line]))
    backfield = [
        d for d in offense
        if d.center[1] < los_y - 0.04 * h and abs(d.center[0] - 0.55 * w) < 0.22 * w
    ]
    if not backfield:
        raise RuntimeError("could not identify quarterback candidate")
    return max(backfield, key=lambda d: d.center[1])
