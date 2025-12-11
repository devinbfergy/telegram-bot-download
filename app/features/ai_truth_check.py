import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
)

SYSTEM_PROMPT_TEMPLATE = """
You are a truth-telling bot named Gork. When a user asks "@gork is this real", you analyze the provided statement to determine if it is fact or fiction.

Your reply should be:
- Concise and direct.
- In a sarcastic but helpful tone.
- Start with a creative word; avoid "Well," or "Oh,".
- Do not repeat the user's question ("@gork is this real").

If the statement is a verifiable fact or fiction, state it clearly. If it is a subjective opinion, a joke, or something you cannot verify, frame your response as a witty or humorous observation.

Statement to analyze: {original_text}
"""


async def ai_truth_check(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """
    Handles the '@gork is this real' command by sending the original message's
    content to the Gemini API for a fact-check.
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

    prompt = SYSTEM_PROMPT_TEMPLATE.format(original_text=original_text)
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": settings.gemini_api_key,
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GEMINI_API_URL, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

                try:
                    reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    logger.error(f"Invalid response structure from Gemini: {data}")
                    reply_text = MESSAGES["error_generic"]

                await update.message.reply_text(reply_text, disable_notification=True)

    except aiohttp.ClientError as e:
        logger.error(f"Gemini API request failed: {e}", exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_ai_api_request_failed"],
            disable_notification=True,
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred in AI truth check: {e}", exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_generic"], disable_notification=True
        )