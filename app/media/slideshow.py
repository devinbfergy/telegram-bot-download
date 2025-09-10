from __future__ import annotations
from pathlib import Path
from typing import Sequence
import subprocess, shutil, tempfile
from app.core.logging import get_logger

log = get_logger(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

def build_slideshow(images: Sequence[Path], out_path: Path) -> Path:
    if not images:
        raise ValueError("No images for slideshow")
    if len(images) == 1:
        # single image -> extend duration by creating short video
        return _single_image_to_video(images[0], out_path)
    try:
        return _images_to_video(images, out_path)
    except Exception as e:  # noqa: BLE001
        log.exception("slideshow.ffmpeg_fallback count=%d", len(images))
        out_path.write_text("slideshow placeholder\n")
        return out_path

def _single_image_to_video(image: Path, out_path: Path) -> Path:
    cmd = [FFMPEG_BIN, "-y", "-loop", "1", "-i", str(image), "-t", "5", "-vf", "format=yuv420p", str(out_path)]
    subprocess.check_call(cmd)
    return out_path

def _images_to_video(images: Sequence[Path], out_path: Path) -> Path:
    with tempfile.TemporaryDirectory() as td:
        list_file = Path(td) / "list.txt"
        with list_file.open('w', encoding='utf-8') as f:
            for img in images:
                f.write(f"file '{img.as_posix()}'\n")
                f.write("duration 2.5\n")
        # last image duration duplication per ffmpeg concat demuxer rules
        with list_file.open('a', encoding='utf-8') as f:
            f.write(f"file '{images[-1].as_posix()}'\n")
        cmd = [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-vf", "format=yuv420p", str(out_path)]
        subprocess.check_call(cmd)
    return out_path
