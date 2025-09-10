from __future__ import annotations
from pathlib import Path
import subprocess, shutil
from app.core.logging import get_logger

log = get_logger(__name__)
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

def ensure_mp4(video: Path) -> Path:
    if video.suffix.lower() == ".mp4":
        return video
    target = video.with_suffix(".mp4")
    try:
        subprocess.check_call([FFMPEG_BIN, "-y", "-i", str(video), "-c", "copy", str(target)])
        return target
    except Exception:  # noqa: BLE001
        log.exception("postprocess.ensure_mp4_fallback file=%s", video)
        return video

def normalize_audio(video: Path) -> Path:
    target = video.with_name(video.stem + ".norm.mp4")
    try:
        subprocess.check_call([FFMPEG_BIN, "-y", "-i", str(video), "-af", "loudnorm", "-c:v", "copy", str(target)])
        return target
    except Exception:  # noqa: BLE001
        log.debug("postprocess.normalize_skip file=%s", video)
        return video
