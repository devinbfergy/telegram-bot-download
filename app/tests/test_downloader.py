from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from yt_dlp.utils import DownloadError

from app.config.settings import AppSettings
from app.media.downloader import Downloader
from app.telegram_bot.status_messenger import StatusMessenger


@pytest.fixture
def settings():
    return AppSettings()


@pytest.fixture
def status_messenger():
    return MagicMock(spec=StatusMessenger)


@pytest.mark.asyncio
@patch("app.media.downloader.Downloader._run_ytdlp_download")
@patch("app.media.downloader.is_youtube_shorts_url", return_value=False)
@patch("app.media.downloader.is_slideshow", return_value=False)
@patch("app.media.downloader.detect_frozen_frames", return_value=False)
@patch("app.media.downloader.Path")
async def test_downloader_success_case(
    MockPath,
    mock_detect_frozen,
    mock_is_slideshow,
    mock_is_shorts,
    mock_to_thread,
    settings,
    status_messenger,
):
    # Arrange
    downloader = Downloader(settings, status_messenger)
    url = "http://example.com/video.mp4"
    message = AsyncMock()

    mock_path_instance = MockPath.return_value
    mock_path_instance.exists.return_value = True
    mock_path_instance.stat.return_value.st_size = 10 * 1024 * 1024  # 10MB
    mock_path_instance.open.return_value = MagicMock()

    mock_to_thread.return_value = {
        "id": "test_id",
        "ext": "mp4",
    }

    # Act
    await downloader.download_and_send_media(url, message)

    # Assert
    from app.config.strings import MESSAGES

    status_messenger.edit_message.assert_any_call(MESSAGES["downloading"])
    status_messenger.edit_message.assert_any_call(MESSAGES["uploading"])
    message.reply_video.assert_called_once()
    status_messenger.delete_status_message.assert_called_once()


@pytest.mark.asyncio
@patch("app.media.downloader.Downloader._run_ytdlp_download")
@patch("app.media.downloader.is_youtube_shorts_url", return_value=False)
@patch("app.media.downloader.is_slideshow", return_value=False)
@patch("app.media.downloader.detect_frozen_frames", side_effect=[True, False])
@patch("app.media.downloader.Path")
async def test_downloader_frozen_frame_fallback(
    MockPath,
    mock_detect_frozen,
    mock_is_slideshow,
    mock_is_shorts,
    mock_run_ytdlp,
    settings,
    status_messenger,
):
    # Arrange
    downloader = Downloader(settings, status_messenger)
    url = "http://example.com/frozen.mp4"
    message = AsyncMock()

    mock_path_instance = MockPath.return_value
    mock_path_instance.exists.return_value = True
    mock_path_instance.stat.return_value.st_size = 10 * 1024 * 1024
    mock_path_instance.open.return_value = MagicMock()

    mock_run_ytdlp.return_value = {"id": "frozen_id", "ext": "mp4"}

    # Act
    await downloader.download_and_send_media(url, message)

    # Assert
    from app.config.strings import MESSAGES

    status_messenger.edit_message.assert_any_call(MESSAGES["downloading"])
    status_messenger.edit_message.assert_any_call(MESSAGES["frozen_frame_retry"])
    status_messenger.edit_message.assert_any_call(MESSAGES["uploading"])
    message.reply_video.assert_called_once()


@pytest.mark.asyncio
@patch(
    "app.media.downloader.Downloader._run_ytdlp_download",
    side_effect=DownloadError("Test error"),
)
@patch("app.media.downloader.download_and_send_with_gallery_dl", new_callable=AsyncMock)
async def test_downloader_ytdlp_fails_fallback_to_gallery_dl(
    mock_gallery_dl, mock_run_ytdlp, settings, status_messenger
):
    # Arrange
    downloader = Downloader(settings, status_messenger)
    url = "http://example.com/bad_video.mp4"
    message = AsyncMock()

    # Act
    await downloader.download_and_send_media(url, message)

    # Assert
    from app.config.strings import MESSAGES

    status_messenger.edit_message.assert_called_once_with(MESSAGES["downloading"])
    mock_gallery_dl.assert_called_once_with(
        url, message, status_messenger, settings, purpose="fallback"
    )
