from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.features.ai_truth_check import ai_truth_check


@pytest.fixture
def settings():
    return AppSettings(gemini_api_key="test_key")


def _make_session_mock(MockClientSession, mock_response):
    """Wire up the three-layer aiohttp async context manager mock."""
    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_ctx


@pytest.mark.asyncio
@patch(
    "app.features.ai_truth_check.get_recent_messages",
    new_callable=AsyncMock,
    return_value=[],
)
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_success(MockClientSession, _mock_db, settings):
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "candidates": [
                {"content": {"parts": [{"text": "Indeed, the sky is blue."}]}}
            ]
        }
    )
    _make_session_mock(MockClientSession, mock_response)

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        "Indeed, the sky is blue.", disable_notification=True
    )


@pytest.mark.asyncio
@patch(
    "app.features.ai_truth_check.get_recent_messages",
    new_callable=AsyncMock,
    return_value=[],
)
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_api_failure(MockClientSession, _mock_db, settings):
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientError("API Error")
    )
    _make_session_mock(MockClientSession, mock_response)

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_ai_api_request_failed"],
        disable_notification=True,
    )


@pytest.mark.asyncio
async def test_ai_truth_check_no_message():
    update = MagicMock(spec=Update)
    update.message = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")
    await ai_truth_check(update, context, settings)
    # Should return early without calling any API


@pytest.mark.asyncio
async def test_ai_truth_check_no_reply():
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")
    await ai_truth_check(update, context, settings)
    # Should return early without calling any API


@pytest.mark.asyncio
async def test_ai_truth_check_no_text():
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
@patch(
    "app.features.ai_truth_check.get_recent_messages",
    new_callable=AsyncMock,
    return_value=[],
)
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_invalid_response_structure(MockClientSession, _mock_db):
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Is the sky blue?"
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    settings = AppSettings(gemini_api_key="test_key")

    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json = AsyncMock(return_value={"invalid": "structure"})
    _make_session_mock(MockClientSession, mock_response)

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_generic"],
        disable_notification=True,
    )


@pytest.mark.asyncio
@patch(
    "app.features.ai_truth_check.get_recent_messages",
    new_callable=AsyncMock,
    return_value=[],
)
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_uses_caption_when_no_text(MockClientSession, _mock_db):
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
    _make_session_mock(MockClientSession, mock_response)

    await ai_truth_check(update, context, settings)

    update.message.reply_text.assert_called_once_with(
        "Response to caption",
        disable_notification=True,
    )
