from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from .camera_director import choose_camera
    from .media_sync import sync_pair
except ImportError:  # standalone prototype execution
    from camera_director import choose_camera
    from media_sync import sync_pair


def _overlay(path: Path, angle: str, label: str) -> None:
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    if angle == "wide":
        box = (520, 210, 815, 500)
        arrow = [(890, 250), (790, 310), (815, 285), (775, 325), (830, 315)]
    else:
        box = (430, 250, 850, 545)
        arrow = [(940, 330), (805, 370), (835, 340), (785, 380), (845, 382)]
    draw.rounded_rectangle(box, radius=26, outline=(255, 224, 0, 235), width=8)
    draw.polygon(arrow, fill=(255, 224, 0, 235))
    draw.rounded_rectangle((28, 28, 620, 82), radius=12, fill=(0, 0, 0, 185))
    draw.text((48, 40), label, fill=(255, 255, 255, 255), font=font)
    im.save(path)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render_proof(wide: str, end_zone: str, output: str, narration: str | None = None) -> dict:
    sync = sync_pair(wide, end_zone)
    pre = 2.4
    aligned_wide = max(0.0, sync.reference_snap_sec - pre)
    aligned_tight = max(0.0, sync.secondary_snap_sec - pre)

    available = {"wide", "end_zone"}
    plan = [
        (choose_camera("formation spacing and coverage", available), 0.0, 3.3),
        (choose_camera("blocking protection and run fit", available), 3.3, 7.3),
        (choose_camera("route spacing and play development", available), 7.3, 11.3),
    ]

    with tempfile.TemporaryDirectory(prefix="multiview_") as td:
        td = Path(td)
        wide_overlay = td / "wide.png"
        tight_overlay = td / "tight.png"
        _overlay(wide_overlay, "wide", "WIDE - FORMATION / SPACING")
        _overlay(tight_overlay, "end_zone", "END ZONE - BLOCKING / RUN FIT")

        pieces = []
        for idx, (decision, start, end) in enumerate(plan):
            src = wide if decision.angle == "wide" else end_zone
            base = aligned_wide if decision.angle == "wide" else aligned_tight
            overlay = wide_overlay if decision.angle == "wide" else tight_overlay
            duration = end - start
            piece = td / f"piece_{idx}.mp4"
            _run([
                "ffmpeg", "-y", "-ss", f"{base + start:.3f}", "-t", f"{duration:.3f}", "-i", src,
                "-loop", "1", "-i", str(overlay),
                "-filter_complex", "[0:v]scale=1280:720,setsar=1[v];[v][1:v]overlay=0:0:shortest=1[outv]",
                "-map", "[outv]", "-an", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(piece),
            ])
            pieces.append(piece)

        concat = td / "concat.txt"
        concat.write_text("\n".join(f"file '{p}'" for p in pieces) + "\n")
        silent = td / "silent.mp4"
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])

        if narration:
            _run([
                "ffmpeg", "-y", "-i", str(silent), "-i", narration,
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                "-af", "apad", "-shortest", output,
            ])
        else:
            Path(output).write_bytes(silent.read_bytes())

    return {
        "sync": sync.to_dict(),
        "camera_plan": [{"angle": d.angle, "reason": d.reason, "start": s, "end": e} for d, s, e in plan],
        "output": output,
    }
