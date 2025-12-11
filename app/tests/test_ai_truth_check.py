from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.features.ai_truth_check import ai_truth_check
from app.config.strings import MESSAGES


@pytest.fixture
def settings():
    return AppSettings(gemini_api_key="test_key")


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_success(MockClientSession, settings):
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Create properly nested async context manager mocks
    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "candidates": [
                {"content": {"parts": [{"text": "Indeed, the sky is blue."}]}}
            ]
        }
    )

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_context)

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_context

    # Act
    await ai_truth_check(update, context, settings)

    # Assert
    update.message.reply_text.assert_called_once_with(
        "Indeed, the sky is blue.", disable_notification=True
    )


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_api_failure(MockClientSession, settings):
    # Arrange
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Mock response that raises on raise_for_status (synchronous method)
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientError("API Error")
    )

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_context)

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_context

    # Act
    await ai_truth_check(update, context, settings)

    # Assert
    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_ai_api_request_failed"],
        disable_notification=True,
    )


@pytest.mark.asyncio
async def test_ai_truth_check_no_message():
    # Test when there's no message
    update = MagicMock(spec=Update)
    update.message = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    await ai_truth_check(update, context, settings)
    # Should return early without calling any API


@pytest.mark.asyncio
async def test_ai_truth_check_no_reply():
    # Test when there's no reply_to_message
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    await ai_truth_check(update, context, settings)
    # Should return early without calling any API


@pytest.mark.asyncio
async def test_ai_truth_check_no_text():
    # Test when reply has no text or caption
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = None
    update.message.reply_to_message.caption = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_no_text"],
        disable_notification=True,
    )


@pytest.mark.asyncio
async def test_ai_truth_check_no_api_key():
    # Test when Gemini API key is not configured
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="")

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_ai_features_not_configured"],
        disable_notification=True,
    )


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_invalid_response_structure(MockClientSession):
    # Test when API returns invalid response structure
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    # Mock response with invalid structure
    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(return_value={"invalid": "structure"})

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_context)

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_context

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_generic"],
        disable_notification=True,
    )


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_uses_caption_when_no_text(MockClientSession):
    # Test that caption is used when text is not available
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = None
    update.message.reply_to_message.caption = "Caption text"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "candidates": [{"content": {"parts": [{"text": "Response to caption"}]}}]
        }
    )

    mock_post_context = AsyncMock()
    mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_context)

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_context

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        "Response to caption",
        disable_notification=True,
    )
