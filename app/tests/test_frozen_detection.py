import subprocess
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.media.inspection import detect_frozen_frames
from app.media.slideshow import create_slideshow_from_media


@patch("app.media.slideshow.subprocess.run")
def test_slideshow_uses_configured_ffmpeg_timeout(mock_run, tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg")
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    output = tmp_path / "output.mp4"

    def fake_run(command, **kwargs):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="10.0")
        Path(command[-1]).touch()
        return subprocess.CompletedProcess(command, 0)

    mock_run.side_effect = fake_run

    assert create_slideshow_from_media([image], audio, output, timeout=73) is True
    assert all(call.kwargs["timeout"] == 73 for call in mock_run.call_args_list)


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
