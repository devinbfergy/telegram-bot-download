"""
Gemini-powered responder for @gork and @guys_being_dudes_bot mentions.

When either bot is @-mentioned (or a message arrives from @guys_being_dudes_bot),
this module:
  1. Fetches the last 10 minutes of messages from the SQLite store as context.
  2. Injects that history into a system prompt so Gork can reply in character.
  3. Calls Gemini flash and sends the reply.
"""

from __future__ import annotations

import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.utils.database import StoredMessage, get_recent_messages

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:generateContent"
)

_SYSTEM_PROMPT = """\
You are Gork, a sarcastic, dry-witted bot embedded in a private group chat \
of friends. You speak in short, punchy lines — no more than 2-3 sentences. \
You never introduce yourself unprompted. You are self-aware but not annoying \
about it. When you don't have enough context you make a joke rather than \
pretending you know things you don't.

Recent chat history (last 10 minutes):
{chat_history}

Now respond to the following message. Stay in character.\
"""


def _format_history(messages: list[StoredMessage]) -> str:
    if not messages:
        return "(no recent messages — you're flying blind)"
    lines: list[str] = []
    for msg in messages:
        display_name = msg.username or msg.first_name or "unknown"
        lines.append(f"{display_name}: {msg.message_text}")
    return "\n".join(lines)


async def respond_to_mention(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    settings: AppSettings,
) -> None:
    """
    Generate a context-aware Gemini reply for an @gork or @guys_being_dudes_bot
    mention, using the last 10 minutes of chat history as context.
    """
    if not update.message:
        return

    # Prefer the text of the message; fall back to captions (photos, videos).
    trigger_text = update.message.text or update.message.caption or ""

    if not settings.gemini_api_key:
        logger.warning("mention_responder: Gemini API key not set")
        await update.message.reply_text(
            MESSAGES["error_ai_features_not_configured"],
            disable_notification=True,
        )
        return

    chat_id = update.effective_chat.id
    db_path = str(settings.db_path)

    recent = await get_recent_messages(db_path, chat_id, minutes=10)
    history_block = _format_history(recent)

    full_prompt = _SYSTEM_PROMPT.format(chat_history=history_block)
    if trigger_text:
        full_prompt += f"\n\nMessage: {trigger_text}"

    api_url = f"{GEMINI_API_URL}?key={settings.gemini_api_key}"
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        # Enable Google Search grounding so Gork can pull in current info.
        "tools": [{"googleSearch": {}}],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers={"Content-Type": "application/json"},
                json=payload,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        try:
            reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            logger.error("mention_responder: unexpected Gemini response shape: %s", data)
            reply_text = MESSAGES["error_generic"]

        await update.message.reply_text(reply_text, disable_notification=True)

    except aiohttp.ClientError as exc:
        logger.error("mention_responder: Gemini request failed: %s", exc, exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_ai_api_request_failed"],
            disable_notification=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("mention_responder: unexpected error: %s", exc, exc_info=True)
        await update.message.reply_text(
            MESSAGES["error_generic"],
            disable_notification=True,
        )
