from __future__ import annotations
from pathlib import Path
from statistics import mean

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

try:  # optional hashing via Pillow
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore

from app.config.settings import FROZEN_FRAME


def _frame_hash(frame) -> int:  # simple average hash
    if Image is None:
        return int(frame.mean())  # coarse fallback
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))  # type: ignore
    img = img.resize((8, 8))
    pixels = list(img.getdata())
    avg = mean(pixels)
    bits = ''.join('1' if p > avg else '0' for p in pixels)
    return int(bits, 2)


def detect_frozen_frames(video: Path) -> bool:
    if cv2 is None:
        return False
    cap = cv2.VideoCapture(str(video))  # type: ignore
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    interval = FROZEN_FRAME.get("sample_interval", 15)
    hashes: list[int] = []
    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % int(fps * interval) == 0:
            try:
                hashes.append(_frame_hash(frame))
            except Exception:
                pass
        frame_index += 1
        if len(hashes) >= 5:
            break
    cap.release()
    if len(hashes) < 2:
        return False
    # if all hashes equal => frozen
    return len(set(hashes)) == 1
