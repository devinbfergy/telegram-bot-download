from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.features.github_issue import (
    IssueSummary,
    create_github_issue,
    open_github_issue,
    parse_gemini_response,
    summarize_with_gemini,
)


@pytest.fixture
def settings():
    return AppSettings(
        gemini_api_key="test_gemini_key",
        github_token="test_github_token",
        github_repo="owner/repo",
    )


@pytest.fixture
def settings_no_github():
    return AppSettings(
        gemini_api_key="test_gemini_key",
        github_token="",
        github_repo="",
    )


@pytest.fixture
def settings_no_gemini():
    return AppSettings(
        gemini_api_key="",
        github_token="test_github_token",
        github_repo="owner/repo",
    )


class TestParseGeminiResponse:
    def test_parse_valid_response(self):
        response = """---TITLE---
Test Issue Title
---BODY---
This is the body of the issue.

With multiple lines."""
        result = parse_gemini_response(response)
        assert result is not None
        assert result.title == "Test Issue Title"
        assert "This is the body of the issue." in result.body

    def test_parse_missing_title_marker(self):
        response = """Some random text
---BODY---
Body content"""
        result = parse_gemini_response(response)
        assert result is None

    def test_parse_missing_body_marker(self):
        response = """---TITLE---
Title content"""
        result = parse_gemini_response(response)
        assert result is None

    def test_parse_truncates_long_title(self):
        long_title = "A" * 150
        response = f"""---TITLE---
{long_title}
---BODY---
Body content"""
        result = parse_gemini_response(response)
        assert result is not None
        assert len(result.title) == 100
        assert result.title.endswith("...")


class TestSummarizeWithGemini:
    @pytest.mark.asyncio
    @patch("app.features.github_issue.aiohttp.ClientSession")
    async def test_summarize_success(self, MockClientSession, settings):
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(
            return_value={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": """---TITLE---
Feature Request: Add Dark Mode
---BODY---
Users are requesting dark mode support."""
                                }
                            ]
                        }
                    }
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

        result = await summarize_with_gemini("test conversation", settings)

        assert result is not None
        assert result.title == "Feature Request: Add Dark Mode"
        assert "dark mode" in result.body.lower()

    @pytest.mark.asyncio
    async def test_summarize_no_api_key(self):
        settings = AppSettings(gemini_api_key="")
        result = await summarize_with_gemini("test conversation", settings)
        assert result is None

    @pytest.mark.asyncio
    @patch("app.features.github_issue.aiohttp.ClientSession")
    async def test_summarize_api_error(self, MockClientSession, settings):
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

        result = await summarize_with_gemini("test conversation", settings)
        assert result is None


class TestCreateGithubIssue:
    @pytest.mark.asyncio
    @patch("app.features.github_issue.aiohttp.ClientSession")
    async def test_create_issue_success(self, MockClientSession, settings):
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(
            return_value={
                "html_url": "https://github.com/owner/repo/issues/1",
                "number": 1,
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

        result = await create_github_issue("Test Title", "Test Body", settings)

        assert result is not None
        assert result["html_url"] == "https://github.com/owner/repo/issues/1"

    @pytest.mark.asyncio
    async def test_create_issue_no_token(self, settings_no_github):
        result = await create_github_issue(
            "Test Title", "Test Body", settings_no_github
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("app.features.github_issue.aiohttp.ClientSession")
    async def test_create_issue_retries_on_failure(
        self, MockClientSession, mock_sleep, settings
    ):
        # First two calls fail, third succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 500
        mock_response_fail.text = AsyncMock(return_value="Server Error")

        mock_response_success = AsyncMock()
        mock_response_success.status = 201
        mock_response_success.json = AsyncMock(
            return_value={"html_url": "https://github.com/owner/repo/issues/1"}
        )

        call_count = 0

        async def mock_aenter(self_arg=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return mock_response_fail
            return mock_response_success

        mock_post_context = AsyncMock()
        mock_post_context.__aenter__ = mock_aenter
        mock_post_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_context)

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)

        MockClientSession.return_value = mock_session_context

        result = await create_github_issue("Test Title", "Test Body", settings)

        assert result is not None
        assert call_count == 3

    @pytest.mark.asyncio
    @patch("app.features.github_issue.aiohttp.ClientSession")
    async def test_create_issue_no_retry_on_client_error(
        self, MockClientSession, settings
    ):
        # 400 errors should not be retried (except 403 rate limit)
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad Request")

        mock_post_context = AsyncMock()
        mock_post_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_post_context)

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)

        MockClientSession.return_value = mock_session_context

        result = await create_github_issue("Test Title", "Test Body", settings)

        assert result is None
        # Should only be called once (no retries for 4xx errors)
        mock_session.post.assert_called_once()


class TestOpenGithubIssue:
    @pytest.mark.asyncio
    async def test_no_message(self, settings):
        update = MagicMock(spec=Update)
        update.message = None
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings)
        # Should return early without error

    @pytest.mark.asyncio
    async def test_no_github_config(self, settings_no_github):
        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings_no_github)

        update.message.reply_text.assert_called_once_with(
            MESSAGES["error_github_not_configured"], disable_notification=True
        )

    @pytest.mark.asyncio
    async def test_no_gemini_config(self, settings_no_gemini):
        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings_no_gemini)

        update.message.reply_text.assert_called_once_with(
            MESSAGES["error_ai_features_not_configured"], disable_notification=True
        )

    @pytest.mark.asyncio
    @patch("app.features.github_issue.fetch_recent_messages")
    async def test_no_messages_found(self, mock_fetch, settings):
        mock_fetch.return_value = []

        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        status_message = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_message)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings)

        status_message.edit_text.assert_called_with(
            MESSAGES["error_github_no_messages"]
        )

    @pytest.mark.asyncio
    @patch("app.features.github_issue.create_github_issue")
    @patch("app.features.github_issue.summarize_with_gemini")
    @patch("app.features.github_issue.fetch_recent_messages")
    async def test_full_success_flow(
        self, mock_fetch, mock_summarize, mock_create, settings
    ):
        mock_fetch.return_value = ["@user1: Hello", "@user2: We need a new feature"]
        mock_summarize.return_value = IssueSummary(
            title="Feature Request", body="Users want a new feature"
        )
        mock_create.return_value = {
            "html_url": "https://github.com/owner/repo/issues/42"
        }

        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        status_message = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_message)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings)

        # Verify the success message was sent
        status_message.edit_text.assert_called_with(
            MESSAGES["github_issue_created"].format(
                url="https://github.com/owner/repo/issues/42"
            )
        )

    @pytest.mark.asyncio
    @patch("app.features.github_issue.summarize_with_gemini")
    @patch("app.features.github_issue.fetch_recent_messages")
    async def test_summarization_failure(self, mock_fetch, mock_summarize, settings):
        mock_fetch.return_value = ["@user1: Hello"]
        mock_summarize.return_value = None

        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        status_message = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_message)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings)

        status_message.edit_text.assert_called_with(
            MESSAGES["error_github_summarization_failed"]
        )

    @pytest.mark.asyncio
    @patch("app.features.github_issue.create_github_issue")
    @patch("app.features.github_issue.summarize_with_gemini")
    @patch("app.features.github_issue.fetch_recent_messages")
    async def test_github_api_failure(
        self, mock_fetch, mock_summarize, mock_create, settings
    ):
        mock_fetch.return_value = ["@user1: Hello"]
        mock_summarize.return_value = IssueSummary(title="Title", body="Body")
        mock_create.return_value = None

        update = MagicMock(spec=Update)
        update.message = AsyncMock()
        status_message = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_message)
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        await open_github_issue(update, context, settings)

        status_message.edit_text.assert_called_with(MESSAGES["error_github_api_failed"])
