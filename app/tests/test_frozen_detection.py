from pathlib import Path
from app.media.inspection import detect_frozen_frames


def test_detect_frozen_frames_placeholder(tmp_path: Path):
    dummy = tmp_path / "video.mp4"
    dummy.write_text("placeholder")
    assert detect_frozen_frames(dummy) is False
