import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import Application, ContextTypes

from app.config.settings import AppSettings
from app.telegram_bot.handlers import (
    handle_bad_bot_reply,
    handle_gork_is_this_real,
    handle_message,
    start,
)


@pytest.fixture
def settings():
    """Provide a default AppSettings instance for tests."""
    return AppSettings()


@pytest.mark.asyncio
async def test_start_handler():
    """
    Test that the start handler replies with the correct welcome message.
    """
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_html = AsyncMock()

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Act
    await start(update, context)

    # Assert
    update.message.reply_html.assert_called_once()
    args, kwargs = update.message.reply_html.call_args
    assert "<b>Video Downloader Bot is active!</b>" in args[0]
    assert kwargs["disable_notification"] is True


@pytest.mark.asyncio
@patch("app.telegram_bot.handlers.Downloader")
async def test_handle_message_with_video_url(MockDownloader):
    """
    Test that handle_message correctly processes a video URL.
    """
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345

    application = MagicMock(spec=Application)
    application.settings = {"app_settings": AppSettings()}

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = application
    context.bot = AsyncMock()

    mock_downloader_instance = MockDownloader.return_value
    mock_downloader_instance.download_and_send_media = AsyncMock()

    with (
        patch("app.telegram_bot.handlers.is_video_url", return_value=True),
        patch("app.telegram_bot.handlers.is_image_url", return_value=False),
        patch("app.telegram_bot.handlers.is_tiktok_photo_url", return_value=False),
    ):
        # Act
        await handle_message(update, context)

    # Assert
    MockDownloader.assert_called_once()
    mock_downloader_instance.download_and_send_media.assert_called_once_with(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", update.message
    )


@pytest.mark.asyncio
@patch("app.telegram_bot.handlers.reprocess_bad_bot")
async def test_handle_bad_bot_reply(mock_reprocess, settings):
    """
    Test that handle_bad_bot_reply calls the reprocess feature.
    """
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.text = "bad bot"
    update.message.reply_to_message = MagicMock()

    application = MagicMock(spec=Application)
    application.settings = {"app_settings": settings}

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = application

    # Act
    await handle_bad_bot_reply(update, context)

    # Assert
    mock_reprocess.assert_called_once_with(update, context, settings)


@pytest.mark.asyncio
@patch("app.telegram_bot.handlers.ai_truth_check")
async def test_handle_gork_is_this_real(mock_ai_truth_check, settings):
    """
    Test that handle_gork_is_this_real calls the AI truth check feature.
    """
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.text = "@gork is this real"
    update.message.reply_to_message = MagicMock()

    application = MagicMock(spec=Application)
    application.settings = {"app_settings": settings}

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = application

    # Act
    await handle_gork_is_this_real(update, context)

    # Assert
    mock_ai_truth_check.assert_called_once_with(update, context, settings)
