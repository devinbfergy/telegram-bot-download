from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import AppSettings
from app.features.ai_truth_check import ai_truth_check
from app.features.github_issue import (
    create_github_issue,
    parse_gemini_response,
    summarize_with_gemini,
)
from app.features.good_bot_catgirl import good_bot_catgirl
from app.features.user_memory import call_gemini_for_memory

PRIVATE_SENTINEL = "PRIVATE_AI_CONTENT_7f3d"


def _mock_session(mock_session_cls, response):
    post_context = AsyncMock()
    post_context.__aenter__ = AsyncMock(return_value=response)
    post_context.__aexit__ = AsyncMock(return_value=None)
    session = AsyncMock()
    session.post = MagicMock(return_value=post_context)
    session_context = AsyncMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    mock_session_cls.return_value = session_context


@pytest.mark.asyncio
@patch("app.features.good_bot_catgirl.aiohttp.ClientSession")
async def test_catgirl_does_not_log_private_response_body(mock_session_cls, caplog):
    response = AsyncMock(status=200)
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value={"invalid": PRIVATE_SENTINEL})
    _mock_session(mock_session_cls, response)
    update = MagicMock()
    update.message = AsyncMock()
    update.message.from_user.username = "someone"
    update.message.reply_to_message = None
    update.effective_chat = MagicMock()

    await good_bot_catgirl(
        update, MagicMock(), AppSettings(gemini_api_key="configured")
    )

    assert PRIVATE_SENTINEL not in caplog.text


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.get_recent_messages", new_callable=AsyncMock)
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_truth_check_does_not_log_private_response_body(
    mock_session_cls, mock_recent, caplog
):
    mock_recent.return_value = []
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value={"invalid": PRIVATE_SENTINEL})
    _mock_session(mock_session_cls, response)
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "private question"
    update.message.from_user = None
    update.message.reply_to_message.from_user = None
    update.effective_chat.id = 123

    await ai_truth_check(update, MagicMock(), AppSettings(gemini_api_key="configured"))

    assert PRIVATE_SENTINEL not in caplog.text


@pytest.mark.asyncio
@patch("app.features.user_memory.aiohttp.ClientSession")
async def test_user_memory_does_not_log_private_response_body(mock_session_cls, caplog):
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value={"invalid": PRIVATE_SENTINEL})
    _mock_session(mock_session_cls, response)

    result = await call_gemini_for_memory(
        "private prompt", AppSettings(gemini_api_key="configured")
    )

    assert result is None
    assert PRIVATE_SENTINEL not in caplog.text


@pytest.mark.asyncio
@patch("app.features.github_issue.aiohttp.ClientSession")
async def test_github_summary_does_not_log_private_response_body(
    mock_session_cls, caplog
):
    response = AsyncMock()
    response.raise_for_status = MagicMock()
    response.json = AsyncMock(return_value={"invalid": PRIVATE_SENTINEL})
    _mock_session(mock_session_cls, response)

    result = await summarize_with_gemini(
        "private conversation", AppSettings(gemini_api_key="configured")
    )

    assert result is None
    assert PRIVATE_SENTINEL not in caplog.text


def test_github_parser_does_not_log_private_model_text(caplog):
    assert parse_gemini_response(PRIVATE_SENTINEL) is None
    assert PRIVATE_SENTINEL not in caplog.text


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
@patch("app.features.github_issue.aiohttp.ClientSession")
async def test_github_api_does_not_log_private_error_body(
    mock_session_cls, _mock_sleep, caplog
):
    response = AsyncMock(status=400)
    response.text = AsyncMock(return_value=PRIVATE_SENTINEL)
    _mock_session(mock_session_cls, response)
    settings = AppSettings(github_token="configured", github_repo="owner/repo")

    result = await create_github_issue("private title", "private body", settings)

    assert result is None
    assert PRIVATE_SENTINEL not in caplog.text
