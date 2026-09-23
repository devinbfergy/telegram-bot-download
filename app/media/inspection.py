from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


def _sample_frames(video: Path, max_samples: int = 5) -> list[np.ndarray]:
    """Sample up to max_samples frames evenly distributed across the video."""
    if cv2 is None:
        return []
    cap = cv2.VideoCapture(str(video))  # type: ignore
    if not cap.isOpened():
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []

    # If seeking is supported and video has enough frames, sample across duration
    if total_frames > max_samples:
        ratios = [0.1, 0.3, 0.5, 0.7, 0.9][:max_samples]
        for r in ratios:
            target = int(total_frames * r)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)

    # Fallback to sequential read every 0.5s if seeking yielded fewer than 2 frames
    if len(frames) < 2:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        step = max(1, int(fps * 0.5))
        idx = 0
        frames = []
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if idx % step == 0:
                frames.append(frame)
                if len(frames) >= max_samples:
                    break
            idx += 1

    cap.release()
    return frames


def detect_frozen_frames(video: Path) -> bool:
    """
    Detect if a video consists entirely of frozen/static frames.
    Samples frames across the video and checks if pixel difference is negligible.
    """
    if cv2 is None:
        return False

    frames = _sample_frames(video, max_samples=5)
    if len(frames) < 2:
        return False

    ref_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    for other in frames[1:]:
        other_gray = cv2.cvtColor(other, cv2.COLOR_BGR2GRAY)
        diff = float(cv2.absdiff(ref_gray, other_gray).mean())
        if diff > 1.5:  # Noticeable visual difference between frames
            return False

    return True
