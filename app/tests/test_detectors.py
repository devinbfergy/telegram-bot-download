from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

from app.media.detectors import (
    is_image_url,
    is_slideshow,
    is_tiktok_photo_url,
    is_video_url,
    is_youtube_shorts_url,
)


@patch("app.media.detectors.YoutubeDL")
def test_is_video_basic(mock_ytdl):
    # Mock the YoutubeDL context manager and extract_info method
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {
        "extractor": "youtube",
        "formats": [{"format_id": "best"}],
    }
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert is_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_is_image_basic():
    assert is_image_url("https://foo.bar/pic.png")


def test_is_image_various_extensions():
    assert is_image_url("https://example.com/photo.jpg")
    assert is_image_url("https://example.com/photo.jpeg")
    assert is_image_url("https://example.com/photo.gif")
    assert is_image_url("https://example.com/photo.webp")
    assert is_image_url("https://example.com/photo.bmp")
    assert is_image_url("https://example.com/photo.tiff")


def test_is_image_with_query_params():
    assert is_image_url("https://example.com/photo.jpg?v=1234&size=large")


def test_is_image_case_insensitive():
    assert is_image_url("https://example.com/photo.JPG")
    assert is_image_url("https://example.com/photo.PNG")


def test_is_not_image():
    assert not is_image_url("https://example.com/video.mp4")
    assert not is_image_url("https://example.com/page.html")
    assert not is_image_url("https://example.com/")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_with_generic_extractor(mock_ytdl):
    # Generic extractor should return False
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {
        "extractor": "generic",
        "formats": [{"format_id": "best"}],
    }
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert not is_video_url("https://example.com/page")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_no_formats(mock_ytdl):
    # No formats available should return False
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {
        "extractor": "youtube",
        "formats": [],
    }
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert not is_video_url("https://www.youtube.com/watch?v=invalid")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_with_playlist_entries(mock_ytdl):
    # Playlist with valid video entries should return True
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {
        "extractor": "youtube",
        "entries": [
            {"formats": [{"format_id": "best"}]},
            {"formats": [{"format_id": "best"}]},
        ],
    }
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert is_video_url("https://www.youtube.com/playlist?list=PL123")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_with_direct_url(mock_ytdl):
    # Direct video URL with non-generic extractor should return True
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = {
        "extractor": "http",
        "url": "https://example.com/video.mp4",
    }
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert is_video_url("https://example.com/video.mp4")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_download_error(mock_ytdl):
    # DownloadError should return False
    mock_instance = MagicMock()
    mock_instance.extract_info.side_effect = DownloadError("Network error")
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert not is_video_url("https://invalid.url/video")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_generic_exception(mock_ytdl):
    # Generic exception should return False
    mock_instance = MagicMock()
    mock_instance.extract_info.side_effect = Exception("Unknown error")
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert not is_video_url("https://example.com/error")


@patch("app.media.detectors.YoutubeDL")
def test_is_video_none_info(mock_ytdl):
    # None info should return False
    mock_instance = MagicMock()
    mock_instance.extract_info.return_value = None
    mock_ytdl.return_value.__enter__.return_value = mock_instance

    assert not is_video_url("https://example.com/nothing")


def test_is_youtube_shorts_url():
    assert is_youtube_shorts_url("https://www.youtube.com/shorts/abc123defgh")
    assert is_youtube_shorts_url("https://youtube.com/shorts/abc123defgh")
    assert is_youtube_shorts_url("https://m.youtube.com/shorts/abc123defgh")
    assert is_youtube_shorts_url("http://www.youtube.com/shorts/abc123defgh")


def test_is_not_youtube_shorts_url():
    assert not is_youtube_shorts_url("https://www.youtube.com/watch?v=abc123defgh")
    assert not is_youtube_shorts_url("https://example.com/shorts/abc123defgh")
    assert not is_youtube_shorts_url("https://youtu.be/abc123defgh")  # Regular videos


def test_is_tiktok_photo_url():
    assert is_tiktok_photo_url("https://www.tiktok.com/@user/photo/1234567890")
    assert is_tiktok_photo_url("https://tiktok.com/@username123/photo/9876543210")


def test_is_not_tiktok_photo_url():
    assert not is_tiktok_photo_url("https://www.tiktok.com/@user/video/1234567890")
    assert not is_tiktok_photo_url("https://example.com/@user/photo/1234567890")


def test_is_slideshow_tiktok():
    info_dict = {
        "_type": "playlist",
        "extractor_key": "TikTok",
        "entries": [
            {"ext": "jpg"},
            {"ext": "png"},
            {"ext": "webp"},
        ],
    }
    assert is_slideshow(info_dict)


def test_is_slideshow_instagram():
    info_dict = {
        "_type": "playlist",
        "extractor_key": "Instagram",
        "entries": [
            {"ext": "jpeg"},
            {"ext": "png"},
        ],
    }
    assert is_slideshow(info_dict)


def test_is_not_slideshow_mixed_content():
    info_dict = {
        "_type": "playlist",
        "extractor_key": "TikTok",
        "entries": [
            {"ext": "jpg"},
            {"ext": "mp4"},  # Video mixed with images
        ],
    }
    assert not is_slideshow(info_dict)


def test_is_not_slideshow_wrong_extractor():
    info_dict = {
        "_type": "playlist",
        "extractor_key": "YouTube",
        "entries": [
            {"ext": "jpg"},
        ],
    }
    assert not is_slideshow(info_dict)


def test_is_not_slideshow_empty_entries():
    info_dict = {
        "_type": "playlist",
        "extractor_key": "TikTok",
        "entries": [],
    }
    assert not is_slideshow(info_dict)


def test_is_not_slideshow_invalid_input():
    assert not is_slideshow(None)  # type: ignore[arg-type]
    assert not is_slideshow("not a dict")  # type: ignore[arg-type]
    assert not is_slideshow([])  # type: ignore[arg-type]
