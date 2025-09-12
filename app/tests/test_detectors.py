from ..media.detectors import is_video_url, is_image_url
from ..core.types import MediaKind


def test_is_video_basic():
    assert is_video_url("https://vimeo.com/12345")

def test_is_image_basic():
    assert is_image_url("https://foo.bar/pic.png")
