from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def synthesize_prototype_narration(text: str, output: str | Path, voice: str = "en-US-GuyNeural", rate: str = "+20%") -> str:
    """Prototype zero-key narration. Production voice provider remains pluggable."""
    exe = shutil.which("edge-tts") or str(Path.home() / ".local" / "bin" / "edge-tts")
    if not Path(exe).exists():
        raise RuntimeError("edge-tts prototype narrator is not installed")
    output = str(output)
    subprocess.run([exe, "--voice", voice, "--rate", rate, "--text", text, "--write-media", output], check=True)
    return output
