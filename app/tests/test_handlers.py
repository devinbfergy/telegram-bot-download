from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import Application, ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.telegram_bot.handlers import (
    handle_bad_bot_reply,
    handle_gork_is_this_real,
    handle_message,
    start,
)
from app.telegram_bot.status_messenger import StatusMessenger


@pytest.fixture
def settings():
    """Provide a default AppSettings instance for tests."""
    return AppSettings()


@pytest.mark.asyncio
async def test_terminal_status_is_distinct_from_transient_progress(settings):
    bot = AsyncMock()
    bot.send_message.return_value = AsyncMock(message_id=1)
    status = StatusMessenger(bot, 123, settings)

    await status.show_terminal_error(MESSAGES["error_generic"])

    assert status.has_active_message() is True
    assert status.has_terminal_error() is True
    bot.send_message.return_value.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_status_replaces_stale_message_after_failed_edit(settings):
    bot = AsyncMock()
    stale_message = AsyncMock(message_id=1)
    replacement = AsyncMock(message_id=2)
    bot.send_message.side_effect = [stale_message, replacement]
    bot.edit_message_text.side_effect = RuntimeError("message no longer exists")
    status = StatusMessenger(bot, 123, settings)
    await status.send_message("working")

    await status.show_terminal_error("failed")

    assert status._message is replacement
    assert status.has_terminal_error() is True
    assert bot.send_message.await_args_list[-1].kwargs["text"] == "failed"


@pytest.mark.asyncio
async def test_failed_terminal_replacement_has_no_stale_ownership(settings):
    bot = AsyncMock()
    stale_message = AsyncMock(message_id=1)
    bot.send_message.side_effect = [stale_message, RuntimeError("send failed")]
    bot.edit_message_text.side_effect = RuntimeError("edit failed")
    status = StatusMessenger(bot, 123, settings)
    await status.send_message("working")

    await status.show_terminal_error("failed")

    assert status.has_active_message() is False
    assert status.has_terminal_error() is False


@pytest.mark.asyncio
async def test_successful_progress_after_terminal_can_be_cleaned_up(settings):
    bot = AsyncMock()
    message = AsyncMock(message_id=1)
    bot.send_message.return_value = message
    status = StatusMessenger(bot, 123, settings)
    await status.show_terminal_error("failed")

    await status.edit_message("retrying")
    await status.delete_status_message()

    assert status.has_active_message() is False
    assert status.has_terminal_error() is False
    message.delete.assert_awaited_once()


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
@patch("app.telegram_bot.handlers.run_blocking", new_callable=AsyncMock)
@patch("app.telegram_bot.handlers.Downloader")
async def test_handle_message_with_video_url(MockDownloader, mock_run_blocking):
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
    mock_run_blocking.return_value = True

    with (
        patch(
            "app.telegram_bot.handlers.is_video_url", return_value=True
        ) as mock_is_video,
        patch("app.telegram_bot.handlers.is_image_url", return_value=False),
        patch("app.telegram_bot.handlers.is_tiktok_photo_url", return_value=False),
    ):
        # Act
        await handle_message(update, context)

    # Assert
    MockDownloader.assert_called_once()
    mock_run_blocking.assert_awaited_once_with(
        mock_is_video,
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        application.settings["app_settings"].timeouts["yt_dlp"],
    )
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
