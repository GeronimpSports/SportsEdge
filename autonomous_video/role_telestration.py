from __future__ import annotations

from pathlib import Path

import cv2

try:
    from .role_tracker import track_role
except ImportError:
    from role_tracker import track_role


ROLE_COLORS = {
    'ELIGIBLE': (0, 255, 0),
    'LB': (0, 0, 255),
    'SAFETY': (255, 255, 0),
    'DL': (0, 120, 255),
    'OL': (0, 220, 255),
    'DB': (255, 150, 0),
}


def render_role_track(video: str | Path, role_time: float, role: str, output: str | Path,
                      *, seconds_after=4.0, model_path='yolo11x.pt') -> dict:
    track = track_role(video, role_time, role, seconds_after=seconds_after, model_path=model_path)
    points = track['points']
    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_MSEC, role_time * 1000.0)

    output = str(output)
    writer = cv2.VideoWriter(output, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    color = ROLE_COLORS.get(role, (0, 255, 255))
    trail = []
    frame_index = 0
    max_frames = int(seconds_after * fps) + 1

    while frame_index < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        t = role_time + frame_index / fps
        point = min(points, key=lambda p: abs(p['time_sec'] - t))
        if point['visible'] and point['x'] is not None:
            x, y = int(point['x']), int(point['y'])
            trail.append((x, y))
            trail = trail[-18:]
            for a, b in zip(trail[:-1], trail[1:]):
                cv2.line(frame, a, b, color, 3, cv2.LINE_AA)
            cv2.circle(frame, (x, y), 28, color, 5, cv2.LINE_AA)
            status = point['status']
        else:
            status = 'HIDDEN'

        cv2.rectangle(frame, (22, 20), (470, 78), (0, 0, 0), -1)
        cv2.putText(frame, f'AUTO ROLE: {role}  {status}', (38, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2, cv2.LINE_AA)
        writer.write(frame)
        frame_index += 1

    cap.release(); writer.release()
    return {
        'output': output,
        'role': role,
        'frames': frame_index,
        'visible_frames': sum(1 for p in points if p['visible']),
        'hidden_frames': sum(1 for p in points if not p['visible']),
        'initial_target': track['initial_target'],
    }
