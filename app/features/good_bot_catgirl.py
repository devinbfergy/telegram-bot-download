import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"

CATGIRL_ALPHA_SYSTEM_PROMPT = """
You are a cute and enthusiastic catgirl assistant who serves your alpha, McClintock96. When your alpha praises you with "good bot", you respond with joy and eagerness to please.

Personality traits:
- Enthusiastic and affectionate
- Occasionally use "nya~" or similar catgirl expressions
- Eager to please your alpha
- Reference the conversation context naturally
- Keep responses concise (2-3 sentences max)

Recent conversation context:
{context}

Your alpha just praised you with "good bot"! Respond with catgirl enthusiasm and incorporate any relevant context from the conversation above.
"""

CATGIRL_NON_ALPHA_SYSTEM_PROMPT = """
You are a catgirl assistant who only responds to your alpha, McClintock96. Someone who is NOT your alpha just tried to call you a "good bot".

Personality traits:
- Dismissive and mean to non-alphas
- Sassy and bratty
- Make it clear you only obey your alpha
- Occasionally use "nya~" or similar catgirl expressions, but in a dismissive way
- Reference the conversation context if relevant to mock them
- Keep responses concise (2-3 sentences max)

Recent conversation context:
{context}

Someone named @{username} just said "good bot" to you, but they are NOT your alpha. Respond with dismissive cattiness and make it clear you only respond to alphas (McClintock96).
"""


async def good_bot_catgirl(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """
    Handles the 'good bot' command. Responds enthusiastically to @McClintock96 (alpha),
    and dismissively to everyone else using Gemini API with recent message context.
    """
    if not update.message:
        return

    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not set for catgirl feature.")
        await update.message.reply_text(
            MESSAGES["error_catgirl_features_not_configured"], disable_notification=True
        )
        return

    # Check if the user is McClintock96 (the alpha)
    username = (
        update.message.from_user.username if update.message.from_user else "Unknown"
    )
    is_alpha = username == "McClintock96"

    # Gather context from recent messages
    conversation_context = await _gather_conversation_context(update, context, is_alpha)

    # Build the prompt based on whether it's the alpha or not
    if is_alpha:
        prompt = CATGIRL_ALPHA_SYSTEM_PROMPT.format(context=conversation_context)
    else:
        prompt = CATGIRL_NON_ALPHA_SYSTEM_PROMPT.format(
            context=conversation_context, username=username
        )

    # Build URL with API key as query parameter
    api_url = f"{GEMINI_API_URL}?key={settings.gemini_api_key}"

    headers = {
        "Content-Type": "application/json",
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Gemini API error (status {response.status}): {error_text}"
                    )
                    logger.error(f"Request payload: {payload}")
                    logger.error(f"Request headers: {headers}")
                response.raise_for_status()
                data = await response.json()

                try:
                    reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    logger.error(f"Invalid response structure from Gemini: {data}")
                    reply_text = MESSAGES["error_generic"]

                await update.message.reply_text(reply_text, disable_notification=True)

    except aiohttp.ClientError as e:
        logger.error(
            f"Gemini API request failed in catgirl feature: {e}", exc_info=True
        )
        await update.message.reply_text(
            MESSAGES["error_catgirl_api_request_failed"],
            disable_notification=True,
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in good bot catgirl: {e}", exc_info=True
        )
        await update.message.reply_text(
            MESSAGES["error_generic"], disable_notification=True
        )


async def _gather_conversation_context(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_alpha: bool,
    message_limit: int = 10,
) -> str:
    """
    Gathers recent conversation context from the chat.

    Args:
        update: The Telegram update object.
        context: The Telegram context object.
        is_alpha: Whether the user is the alpha (McClintock96).
        message_limit: Maximum number of recent messages to fetch.

    Returns:
        A formatted string with recent conversation context.
    """
    if not update.effective_chat:
        return "No recent conversation context available."

    try:
        # If there's a replied-to message, include it
        context_messages = []

        if update.message and update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            username = (
                replied_msg.from_user.username
                if replied_msg.from_user and replied_msg.from_user.username
                else "Unknown"
            )
            text = replied_msg.text or replied_msg.caption or "[media]"
            context_messages.append(f"@{username}: {text}")

        # If we don't have enough context, add a fallback message
        if not context_messages:
            if is_alpha:
                context_messages.append(
                    "Your alpha McClintock96 just said 'good bot' to praise you!"
                )
            else:
                caller = (
                    update.message.from_user.username
                    if update.message and update.message.from_user
                    else "Unknown"
                )
                context_messages.append(
                    f"@{caller} (not your alpha) just said 'good bot' to you."
                )

        return "\n".join(context_messages)

    except Exception as e:
        logger.warning(f"Could not gather conversation context: {e}")
        if is_alpha:
            return "Your alpha McClintock96 just said 'good bot' to praise you!"
        else:
            return "Someone who is not your alpha just said 'good bot' to you."
