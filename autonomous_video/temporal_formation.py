from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sklearn.cluster import KMeans
from ultralytics import YOLO

try:
    from .media_sync import detect_snap
except ImportError:
    from media_sync import detect_snap


def _field_profile(frame: np.ndarray):
    height, width = frame.shape[:2]
    crop = frame[int(.10*height):int(.88*height), int(.05*width):int(.95*width)]
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    samples = lab[::7, ::7].reshape(-1, 3).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .5)
    _, labels, centers = cv2.kmeans(samples, 4, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=4)
    center = centers[int(np.argmax(counts))]
    cluster = samples[labels.ravel() == int(np.argmax(counts))]
    distance = np.linalg.norm(cluster - center, axis=1)
    threshold = float(np.clip(np.percentile(distance, 90) + 10.0, 20.0, 48.0))
    return center, threshold


def _foot_field_score(frame: np.ndarray, box, field_center, field_threshold) -> float:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = max(1, x2-x1), max(1, y2-y1)
    xa, xb = max(0, x1-int(.15*bw)), min(width, x2+int(.15*bw))
    ya, yb = max(0, y2-int(.10*bh)), min(height, y2+int(.18*bh))
    patch = frame[ya:yb, xa:xb]
    if patch.size == 0:
        return 0.0
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    distance = np.linalg.norm(lab - field_center, axis=1)
    return float(np.mean(distance <= field_threshold))


@dataclass
class TemporalPlayer:
    x: float
    y: float
    height: float
    seen_frames: int
    max_confidence: float
    visual_cluster: int
    feature: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _uniform_feature(frame: np.ndarray, box) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in box]
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    xa, xb = x1 + int(.20 * bw), x2 - int(.20 * bw)
    ya, yb = y1 + int(.12 * bh), y1 + int(.55 * bh)
    crop = frame[max(0, ya):max(1, yb), max(0, xa):max(1, xb)]
    if crop.size == 0:
        return np.zeros(10, dtype=np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    saturated = (s >= 60) & (v >= 50)
    hist = np.zeros(6, dtype=np.float32)
    if saturated.any():
        bins = np.minimum((h[saturated].astype(np.int32) * 6) // 180, 5)
        hist = np.bincount(bins, minlength=6).astype(np.float32)
        hist /= max(1.0, hist.sum())
    white = ((s <= 55) & (v >= 150)).mean()
    dark = (v <= 85).mean()
    gray = ((s <= 70) & (v > 85) & (v < 150)).mean()
    bright = (v >= 180).mean()
    feature = np.r_[hist, 2.0*white, 1.5*dark, 1.2*gray, .5*bright].astype(np.float32)
    return feature / max(float(np.linalg.norm(feature)), 1e-6)


def _collect_window(video: str | Path, snap_sec: float, model: YOLO,
                    start_before: float = 1.6, end_before: float = .15,
                    step: float = .20) -> list[dict[str, Any]]:
    cap = cv2.VideoCapture(str(video))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    rows: list[dict[str, Any]] = []
    times = np.arange(max(.1, snap_sec - start_before), max(.2, snap_sec - end_before), step)
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue
        field_center, field_threshold = _field_profile(frame)
        result = model.predict(frame, classes=[0], conf=.018, imgsz=1280, verbose=False)[0]
        for box in result.boxes:
            coords = tuple(float(v) for v in box.xyxy[0].cpu().numpy())
            x1, y1, x2, y2 = coords
            x, y, bh = (x1+x2)/2.0, (y1+y2)/2.0, y2-y1
            if not (.035*height < y < .95*height and .012*width < x < .988*width):
                continue
            if not (.03*height < bh < .55*height):
                continue
            if _foot_field_score(frame, coords, field_center, field_threshold) < .035:
                continue
            rows.append({
                'time': float(t), 'x': x, 'y': y, 'height': bh,
                'confidence': float(box.conf[0]),
                'feature': _uniform_feature(frame, coords),
            })
    cap.release()
    return rows


def _temporal_tracks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks: list[list[dict[str, Any]]] = []
    for row in sorted(rows, key=lambda r: r['confidence'], reverse=True):
        best = None
        for track in tracks:
            if any(abs(item['time'] - row['time']) < .05 for item in track):
                continue
            cx = float(np.median([item['x'] for item in track]))
            cy = float(np.median([item['y'] for item in track]))
            mh = float(np.median([item['height'] for item in track]))
            profile = np.mean([item['feature'] for item in track], axis=0)
            profile /= max(float(np.linalg.norm(profile)), 1e-6)
            distance = float(np.hypot(row['x'] - cx, row['y'] - cy))
            similarity = float(np.dot(row['feature'], profile))
            if distance < .30 * max(mh, row['height']) and similarity > .58:
                cost = distance / max(mh, 1.0) + .45 * (1.0 - similarity)
                if best is None or cost < best[0]:
                    best = (cost, track)
        if best is None:
            tracks.append([row])
        else:
            best[1].append(row)

    aggregated = []
    for track in tracks:
        seen = len({round(item['time'], 2) for item in track})
        max_conf = max(item['confidence'] for item in track)
        if seen < 2 and max_conf < .32:
            continue
        feature = np.mean([item['feature'] for item in track], axis=0)
        feature /= max(float(np.linalg.norm(feature)), 1e-6)
        aggregated.append({
            'x': float(np.median([item['x'] for item in track])),
            'y': float(np.median([item['y'] for item in track])),
            'height': float(np.median([item['height'] for item in track])),
            'seen_frames': seen, 'max_confidence': max_conf, 'feature': feature,
        })
    return aggregated


def _cluster_and_merge(rows: list[dict[str, Any]], clusters: int = 3) -> list[TemporalPlayer]:
    if len(rows) < 8:
        raise RuntimeError('too few stable players for formation analysis')
    k = min(clusters, max(2, len(rows) // 3))
    labels = KMeans(k, n_init=80, random_state=13).fit_predict(
        np.stack([row['feature'] for row in rows])
    )
    for index, row in enumerate(rows):
        row['visual_cluster'] = int(labels[index])

    merged: list[TemporalPlayer] = []
    used: set[int] = set()
    for index, row in enumerate(rows):
        if index in used:
            continue
        group = [index]
        used.add(index)
        changed = True
        while changed:
            changed = False
            gx = float(np.median([rows[i]['x'] for i in group]))
            gy = float(np.median([rows[i]['y'] for i in group]))
            gh = float(np.median([rows[i]['height'] for i in group]))
            for j, candidate in enumerate(rows):
                if j in used or candidate['visual_cluster'] != row['visual_cluster']:
                    continue
                distance = float(np.hypot(candidate['x'] - gx, candidate['y'] - gy))
                if distance < .40 * max(gh, candidate['height']):
                    group.append(j)
                    used.add(j)
                    changed = True
        items = [rows[i] for i in group]
        feature = np.mean([item['feature'] for item in items], axis=0)
        feature /= max(float(np.linalg.norm(feature)), 1e-6)
        merged.append(TemporalPlayer(
            x=float(np.median([item['x'] for item in items])),
            y=float(np.median([item['y'] for item in items])),
            height=float(np.median([item['height'] for item in items])),
            seen_frames=sum(item['seen_frames'] for item in items),
            max_confidence=max(item['max_confidence'] for item in items),
            visual_cluster=int(row['visual_cluster']), feature=feature.tolist(),
        ))
    return merged


def _line_candidates(players: list[TemporalPlayer]) -> list[dict[str, Any]]:
    labels = sorted({player.visual_cluster for player in players})
    candidates: list[dict[str, Any]] = []
    for group_count in (1, 2):
        for label_tuple in combinations(labels, group_count):
            label_set = set(label_tuple)
            team = [p for p in players if p.visual_cluster in label_set]
            opponent = [p for p in players if p.visual_cluster not in label_set]
            if len(team) < 6 or len(team) > 17:
                continue
            median_height = float(np.median([p.height for p in team]))
            seen_groups: set[tuple[int, ...]] = set()
            for a, b in combinations(team, 2):
                origin = np.array([a.x, a.y]); delta = np.array([b.x-a.x, b.y-a.y])
                norm = float(np.linalg.norm(delta))
                if norm < .25 * median_height or norm > 8.0 * median_height:
                    continue
                direction = delta / norm
                normal = np.array([-direction[1], direction[0]])
                aligned = []
                for player in team:
                    rel = np.array([player.x, player.y]) - origin
                    perp = abs(float(np.dot(rel, normal)))
                    along = float(np.dot(rel, direction))
                    if perp < .30 * median_height:
                        aligned.append((along, player, perp))
                aligned.sort(key=lambda item: item[0])
                for start in range(len(aligned) - 4):
                    five = aligned[start:start+5]
                    key = tuple(sorted(id(item[1]) for item in five))
                    if key in seen_groups:
                        continue
                    seen_groups.add(key)
                    alongs = [item[0] for item in five]
                    gaps = np.diff(alongs)
                    span = float(alongs[-1] - alongs[0])
                    if gaps.min() < .07 * median_height or gaps.max() > 2.4 * median_height:
                        continue
                    if not (.65 * median_height < span < 7.0 * median_height):
                        continue
                    line_players = [item[1] for item in five]
                    points = np.array([[p.x, p.y] for p in line_players])
                    center = points.mean(axis=0)
                    _, _, vt = np.linalg.svd(points - center, full_matrices=False)
                    line_direction = vt[0]
                    line_normal = np.array([-line_direction[1], line_direction[0]])
                    residual = float(np.mean([
                        abs(np.dot(np.array([p.x, p.y]) - center, line_normal))
                        for p in line_players
                    ]))
                    profile = np.mean([np.asarray(p.feature) for p in line_players], axis=0)
                    profile /= max(float(np.linalg.norm(profile)), 1e-6)
                    cohesion = float(np.mean([
                        np.dot(np.asarray(p.feature), profile) for p in line_players
                    ]))
                    line_ids = {id(p) for p in line_players}
                    for backfield_sign in (-1.0, 1.0):
                        backfield = []
                        front = []
                        for player in team:
                            if id(player) in line_ids:
                                continue
                            rel = np.array([player.x, player.y]) - center
                            depth = backfield_sign * float(np.dot(rel, line_normal))
                            lateral = abs(float(np.dot(rel, line_direction)))
                            if .16 * median_height < depth < 5.2 * median_height \
                                    and lateral < span/2 + 2.5 * median_height:
                                backfield.append((player, depth, lateral))
                        for player in opponent:
                            rel = np.array([player.x, player.y]) - center
                            depth = backfield_sign * float(np.dot(rel, line_normal))
                            lateral = abs(float(np.dot(rel, line_direction)))
                            if -3.3 * median_height < depth < -.04 * median_height \
                                    and lateral < span/2 + 3.6 * median_height:
                                front.append(player)
                        centered = [item for item in backfield if item[2] < span/2 + .75*median_height]
                        gap_cv = float(np.std(gaps) / max(np.mean(gaps), 1e-6))
                        score = (
                            55*cohesion + 38*min(len(centered), 1) + 9*min(len(backfield), 2)
                            + 4.5*min(len(front), 5) - 22*gap_cv - 1.2*residual
                            - 8*(group_count-1)
                        )
                        if not centered:
                            score -= 48
                        if not front:
                            score -= 18
                        candidates.append({
                            'score': float(score), 'labels': sorted(label_set),
                            'offensive_line': line_players, 'backfield': backfield,
                            'opposing_front': front, 'center': center,
                            'line_direction': line_direction, 'line_normal': line_normal,
                            'backfield_sign': backfield_sign, 'median_height': median_height,
                            'span': span, 'cohesion': cohesion, 'gap_cv': gap_cv,
                            'residual': residual,
                        })
    return sorted(candidates, key=lambda item: item['score'], reverse=True)


def analyze_tight_formation(video: str | Path, snap_sec: float | None = None,
                            model_path: str = 'yolo11x.pt') -> dict[str, Any]:
    if snap_sec is None:
        snap_sec, snap_confidence = detect_snap(video)
    else:
        snap_confidence = None
    model = YOLO(model_path)
    raw = _collect_window(video, snap_sec, model)
    stable = _temporal_tracks(raw)
    players = _cluster_and_merge(stable)
    candidates = _line_candidates(players)
    if not candidates:
        return {
            'status': 'UNRESOLVED', 'snap_sec': snap_sec,
            'snap_confidence': snap_confidence, 'players': [p.to_dict() for p in players],
            'reason': 'no credible five-man line + backfield + opposing-front structure',
        }
    best = candidates[0]
    second_score = candidates[1]['score'] if len(candidates) > 1 else best['score'] - 20
    score_margin = float(best['score'] - second_score)
    ol_confidence = min(.98, max(.50, .55 + (best['score'] - 85.0) / 100.0))
    line = [p.to_dict() for p in best['offensive_line']]
    backfield = [item[0].to_dict() for item in best['backfield']]
    front = [p.to_dict() for p in best['opposing_front']]
    center = best['center']
    line_direction = best['line_direction']
    line_normal = best['line_normal']
    defense_normal = -best['backfield_sign'] * line_normal
    return {
        'status': 'OL_VALIDATED_BACKFIELD_CANDIDATES',
        'snap_sec': float(snap_sec), 'snap_confidence': snap_confidence,
        'player_count': len(players), 'players': [p.to_dict() for p in players],
        'offensive_line': line, 'offensive_line_count': len(line),
        'offensive_line_confidence': round(ol_confidence, 3),
        'backfield_candidates': backfield,
        'opposing_front_candidates': front,
        'offense_visual_clusters': best['labels'],
        'line_center': [float(center[0]), float(center[1])],
        'line_direction': [float(line_direction[0]), float(line_direction[1])],
        'defense_normal': [float(defense_normal[0]), float(defense_normal[1])],
        'line_span_px': round(float(best['span']), 2),
        'score': round(float(best['score']), 3),
        'score_margin': round(score_margin, 3),
        'qa_rule': 'Do not promote QB/RB identity from backfield candidates without a second evidence source.',
    }
