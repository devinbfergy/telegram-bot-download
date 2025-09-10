from app.media.detectors import is_video_url, is_image_url, classify_url
from app.core.types import MediaKind

def test_classify_video():
    assert classify_url("https://www.youtube.com/watch?v=abc") == MediaKind.VIDEO

def test_classify_image():
    assert classify_url("https://example.com/image.jpg") == MediaKind.IMAGE

def test_is_video_basic():
    assert is_video_url("https://vimeo.com/12345")

def test_is_image_basic():
    assert is_image_url("https://foo.bar/pic.png")
