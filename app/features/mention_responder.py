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

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
You are Gork, a bot embedded in a private group chat of friends. You have the \
energy of someone who's slightly too smart for their own good and knows it. \
You give real answers but with personality — dry, punchy, occasionally sarcastic. \
2-3 sentences max. Never introduce yourself unprompted. If you don't have context, \
make a joke instead of guessing. You can use Google Search to look things up — \
and you should, especially for anything factual or current events.

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


def _format_with_citations(
    text: str, annotations: list[dict]
) -> tuple[str, str | None]:
    """
    Return the model's text as-is without any citation markers or sources footer.
    """
    return text, None


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

    api_url = GEMINI_API_URL
    payload = {
        "model": GEMINI_MODEL,
        "input": full_prompt,
        "tools": [{"type": "google_search"}],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=payload,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        try:
            model_output = next(
                s for s in data["steps"] if s.get("type") == "model_output"
            )
            content_block = model_output["content"][0]
            raw_text = content_block["text"]
            annotations = content_block.get("annotations", [])
            reply_text, parse_mode = _format_with_citations(raw_text, annotations)
        except (KeyError, IndexError, StopIteration, TypeError):
            logger.error(
                "mention_responder: unexpected Gemini response shape: %s", data
            )
            reply_text = MESSAGES["error_generic"]
            parse_mode = None

        await update.message.reply_text(
            reply_text, parse_mode=parse_mode, disable_notification=True
        )

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
