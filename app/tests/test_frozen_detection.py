from pathlib import Path

import cv2
import numpy as np

from app.media.inspection import detect_frozen_frames


def test_detect_frozen_frames_placeholder(tmp_path: Path):
    dummy = tmp_path / "video.mp4"
    dummy.write_text("placeholder")
    assert detect_frozen_frames(dummy) is False


def test_detect_frozen_frames_detects_static_video(tmp_path: Path):
    video_path = tmp_path / "frozen.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (100, 100))
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    for _ in range(60):
        out.write(frame)
    out.release()

    assert detect_frozen_frames(video_path) is True


def test_detect_frozen_frames_detects_moving_video(tmp_path: Path):
    video_path = tmp_path / "moving.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (100, 100))
    for i in range(60):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.circle(frame, (i, 50), 10, (255, 255, 255), -1)
        out.write(frame)
    out.release()

    assert detect_frozen_frames(video_path) is False
