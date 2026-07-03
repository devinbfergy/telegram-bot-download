import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.utils.database import StoredMessage, get_recent_messages

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"

SYSTEM_PROMPT_TEMPLATE = """
You are a truth-telling bot named Gork. When a user asks "@gork is this real", you analyze the provided statement to determine if it is fact or fiction.

Your reply should be:
- Concise and direct.
- In a sarcastic but helpful tone.
- Start with a creative word; avoid "Well," or "Oh,".
- Do not repeat the user's question ("@gork is this real").
- Use the web search results available to you to verify claims before responding.
- If the statement is a verifiable fact or fiction, state it clearly and cite what you found.
- If it is a subjective opinion, a joke, or something you cannot verify, frame your response as a witty or humorous observation.

Recent chat context (last 10 minutes, for background only — do not fact-check this):
{chat_history}

Statement to analyze: {original_text}
"""


def _format_history(messages: list[StoredMessage]) -> str:
    if not messages:
        return "(no recent messages)"
    lines: list[str] = []
    for msg in messages:
        name = msg.username or msg.first_name or "unknown"
        lines.append(f"{name}: {msg.message_text}")
    return "\n".join(lines)


async def ai_truth_check(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """
    Handles the '@gork is this real' command.

    Enhancements over the original:
    - Pulls the last 10 minutes of chat history from SQLite and includes it as
      context so Gork understands what conversation the claim came from.
    - Enables Gemini's built-in Google Search grounding so the model can look
      up current facts before replying.
    """
    if not update.message or not update.message.reply_to_message:
        return

    original_text = (
        update.message.reply_to_message.text or update.message.reply_to_message.caption
    )
    if not original_text:
        await update.message.reply_text(
            MESSAGES["error_no_text"],
            disable_notification=True,
        )
        return

    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not set.")
        await update.message.reply_text(
            MESSAGES["error_ai_features_not_configured"], disable_notification=True
        )
        return

    # Fetch recent chat history for context.
    chat_id = update.effective_chat.id
    recent = await get_recent_messages(str(settings.db_path), chat_id, minutes=10)
    chat_history = _format_history(recent)

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        chat_history=chat_history,
        original_text=original_text,
    )

    api_url = f"{GEMINI_API_URL}?key={settings.gemini_api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        # Enable Google Search grounding (REST API uses camelCase "googleSearch").
        "tools": [{"googleSearch": {}}],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()

        try:
            reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            logger.error("ai_truth_check: unexpected Gemini response shape: %s", data)
            reply_text = MESSAGES["error_generic"]

        await update.message.reply_text(reply_text, disable_notification=True)

    except aiohttp.ClientError as e:
        logger.error("ai_truth_check: Gemini request failed: %s", e, exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_ai_api_request_failed"],
            disable_notification=True,
        )
    except Exception as e:
        logger.error("ai_truth_check: unexpected error: %s", e, exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_generic"], disable_notification=True
        )
