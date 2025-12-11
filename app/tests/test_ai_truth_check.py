from unittest.mock import AsyncMock, MagicMock, patch

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

    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Indeed, the sky is blue."}]}}]
    }

    mock_session = MockClientSession.return_value.__aenter__.return_value
    mock_session.post.return_value.__aenter__.return_value = mock_response

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

    mock_response = AsyncMock()
    mock_response.raise_for_status.side_effect = Exception("API Error")

    mock_session = MockClientSession.return_value.__aenter__.return_value
    mock_session.post.return_value.__aenter__.return_value = mock_response

    # Act
    await ai_truth_check(update, context, settings)

    # Assert
    update.message.reply_text.assert_called_once_with(
        MESSAGES["error_ai_api_request_failed"],
        disable_notification=True,
    )
