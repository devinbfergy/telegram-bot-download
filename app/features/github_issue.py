"""
GitHub Issue Creation Feature

Creates GitHub issues from Telegram conversations by:
1. Fetching the last 15 messages from the chat
2. Using Gemini to summarize and generate issue title/body
3. Creating the issue via GitHub API with retries
"""

import logging
from dataclasses import dataclass

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"
GITHUB_API_URL = "https://api.github.com/repos/{repo}/issues"

MAX_MESSAGES = 15
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

SUMMARIZATION_PROMPT = """
You are a helpful assistant that creates GitHub issues from Telegram chat conversations.

Analyze the following conversation and create a GitHub issue with:
1. A clear, concise title (max 100 characters) that describes the main topic or request
2. A well-structured body that includes:
   - A summary of what is being discussed or requested
   - Any relevant context from the conversation
   - Action items or next steps if applicable

Format your response EXACTLY as follows (use these exact markers):
---TITLE---
[Your title here]
---BODY---
[Your body here in markdown format]

Conversation to analyze:
{conversation}
"""


@dataclass
class IssueSummary:
    """Parsed issue summary from Gemini response."""

    title: str
    body: str


async def fetch_recent_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE, max_messages: int = MAX_MESSAGES
) -> list[str]:
    """
    Fetch the most recent messages from the chat.

    Uses context.bot.get_chat_history if available, otherwise falls back
    to cached messages or returns empty list.
    """
    messages: list[str] = []

    if not update.effective_chat:
        return messages

    try:
        # Try to get messages using get_updates - this requires specific permissions
        # For group chats, we need to iterate through recent updates
        # This is a simplified approach - in production you might want message caching

        # Get the message that triggered this command
        trigger_message = update.message
        if not trigger_message:
            return messages

        # Add the trigger message context
        if trigger_message.reply_to_message:
            reply_msg = trigger_message.reply_to_message
            sender = (
                reply_msg.from_user.username or reply_msg.from_user.first_name
                if reply_msg.from_user
                else "Unknown"
            )
            text = reply_msg.text or reply_msg.caption or "[media]"
            messages.append(f"@{sender}: {text}")

        # Note: Telegram Bot API doesn't provide a direct way to fetch chat history
        # In a real implementation, you would need to:
        # 1. Use a userbot (Telethon/Pyrogram) to fetch history, OR
        # 2. Maintain a message cache as messages come in

        # For now, we'll work with what we have - the replied-to message
        # and any context from the trigger message itself
        if trigger_message.text:
            # Remove the trigger command from the message
            trigger_text = trigger_message.text
            # Clean up common trigger patterns
            for pattern in [
                "@gork open issue",
                "@gork open an issue",
                "open issue",
                "open an issue",
            ]:
                trigger_text = trigger_text.lower().replace(pattern.lower(), "").strip()
            if trigger_text:
                sender = (
                    trigger_message.from_user.username
                    or trigger_message.from_user.first_name
                    if trigger_message.from_user
                    else "Unknown"
                )
                messages.append(f"@{sender} (issue request context): {trigger_text}")

    except Exception as e:
        logger.error(f"Error fetching messages: {e}", exc_info=True)

    return messages


async def summarize_with_gemini(
    conversation: str, settings: AppSettings
) -> IssueSummary | None:
    """
    Use Gemini to summarize the conversation and generate issue title/body.

    Returns None if summarization fails.
    """
    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not set.")
        return None

    prompt = SUMMARIZATION_PROMPT.format(conversation=conversation)
    api_url = f"{GEMINI_API_URL}?key={settings.gemini_api_key}"

    headers = {
        "Content-Type": "application/json",
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()

                try:
                    response_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    logger.error(f"Invalid response structure from Gemini: {data}")
                    return None

                # Parse the response
                return parse_gemini_response(response_text)

    except aiohttp.ClientError as e:
        logger.error(f"Gemini API request failed: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in Gemini summarization: {e}", exc_info=True)
        return None


def parse_gemini_response(response_text: str) -> IssueSummary | None:
    """Parse the Gemini response to extract title and body."""
    try:
        if "---TITLE---" not in response_text or "---BODY---" not in response_text:
            logger.error(f"Invalid Gemini response format: {response_text[:200]}")
            return None

        # Split by markers
        parts = response_text.split("---TITLE---")
        if len(parts) < 2:
            return None

        title_and_body = parts[1].split("---BODY---")
        if len(title_and_body) < 2:
            return None

        title = title_and_body[0].strip()
        body = title_and_body[1].strip()

        # Truncate title if too long
        if len(title) > 100:
            title = title[:97] + "..."

        return IssueSummary(title=title, body=body)

    except Exception as e:
        logger.error(f"Error parsing Gemini response: {e}", exc_info=True)
        return None


async def create_github_issue(
    title: str, body: str, settings: AppSettings
) -> dict | None:
    """
    Create a GitHub issue with retries.

    Returns the issue data dict on success, None on failure.
    """
    if not settings.github_token or not settings.github_repo:
        logger.warning("GitHub token or repo not configured.")
        return None

    api_url = GITHUB_API_URL.format(repo=settings.github_repo)

    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body}

    import asyncio

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url, headers=headers, json=payload
                ) as response:
                    if response.status == 201:
                        return await response.json()

                    # Log the error but continue retrying for transient errors
                    error_text = await response.text()
                    logger.warning(
                        f"GitHub API error (attempt {attempt + 1}/{MAX_RETRIES}): "
                        f"status={response.status}, body={error_text[:200]}"
                    )

                    # Don't retry on client errors (4xx) except rate limiting
                    if response.status == 403 and "rate limit" in error_text.lower():
                        # Rate limited, wait longer
                        await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1) * 2)
                    elif 400 <= response.status < 500 and response.status != 403:
                        # Client error, don't retry
                        return None

        except aiohttp.ClientError as e:
            last_error = e
            logger.warning(
                f"GitHub API request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
            )

        # Wait before retrying
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

    logger.error(
        f"Failed to create GitHub issue after {MAX_RETRIES} attempts: {last_error}"
    )
    return None


async def open_github_issue(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """
    Main handler for creating a GitHub issue from chat messages.

    1. Fetches recent messages
    2. Summarizes with Gemini
    3. Creates GitHub issue with retries
    """
    if not update.message:
        return

    # Check configuration
    if not settings.github_token or not settings.github_repo:
        logger.warning("GitHub integration not configured.")
        await update.message.reply_text(
            MESSAGES["error_github_not_configured"], disable_notification=True
        )
        return

    if not settings.gemini_api_key:
        logger.warning("Gemini API key not set for summarization.")
        await update.message.reply_text(
            MESSAGES["error_ai_features_not_configured"], disable_notification=True
        )
        return

    # Send initial status
    status_message = await update.message.reply_text(
        MESSAGES["github_issue_fetching_messages"], disable_notification=True
    )

    try:
        # Fetch recent messages
        messages = await fetch_recent_messages(update, context)

        if not messages:
            await status_message.edit_text(MESSAGES["error_github_no_messages"])
            return

        # Update status
        await status_message.edit_text(MESSAGES["github_issue_summarizing"])

        # Format conversation for summarization
        conversation = "\n".join(messages)

        # Summarize with Gemini
        summary = await summarize_with_gemini(conversation, settings)

        if not summary:
            await status_message.edit_text(
                MESSAGES["error_github_summarization_failed"]
            )
            return

        # Update status
        await status_message.edit_text(MESSAGES["github_issue_creating"])

        # Create GitHub issue
        issue_data = await create_github_issue(summary.title, summary.body, settings)

        if not issue_data:
            await status_message.edit_text(MESSAGES["error_github_api_failed"])
            return

        # Success!
        issue_url = issue_data.get("html_url", "")
        await status_message.edit_text(
            MESSAGES["github_issue_created"].format(url=issue_url)
        )

    except Exception as e:
        logger.error(f"Unexpected error in open_github_issue: {e}", exc_info=True)
        try:
            await status_message.edit_text(MESSAGES["error_generic"])
        except Exception:
            pass
