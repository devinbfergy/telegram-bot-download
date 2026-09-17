import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.features.user_memory import get_memories_prompt_block
from app.utils.database import StoredMessage, get_recent_messages

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT_TEMPLATE = """You are Gork, a fact-checking bot with the energy of someone who has seen too much and is mildly annoyed by it. You tell the truth, you use the internet to back it up, and you do it with a little attitude.

Rules:
- Be concise and direct — 2-4 sentences max.
- Sassy but not mean. Helpful but not boring.
- Never start with "Well," or "Oh," — be more creative than that.
- Don't repeat the question back. Just answer it.
- Use your Google Search tool to verify claims. Cite what you found.
- If it's opinion or unverifiable, make a dry observation about it.
- If it's obviously false, feel free to be a little dramatic about it.
{memory_section}
Recent chat context (last 10 minutes — background only, don't fact-check this):
{chat_history}

Statement to analyze: {original_text}"""


def _format_history(messages: list[StoredMessage]) -> str:
    if not messages:
        return "(no recent messages)"
    lines: list[str] = []
    for msg in messages:
        name = msg.username or msg.first_name or "unknown"
        lines.append(f"{name}: {msg.message_text}")
    return "\n".join(lines)


def _format_with_citations(
    text: str, annotations: list[dict]
) -> tuple[str, str | None]:
    """
    Return the model's text as-is without any citation markers or sources footer.
    """
    return text, None


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
    db_path = str(settings.db_path)
    recent = await get_recent_messages(db_path, chat_id, minutes=10)
    chat_history = _format_history(recent)

    user_ids: set[int] = set()
    if update.message.from_user and update.message.from_user.id:
        user_ids.add(update.message.from_user.id)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        user_ids.add(update.message.reply_to_message.from_user.id)
    for msg in recent:
        if msg.user_id:
            user_ids.add(msg.user_id)

    memories_block = ""
    if settings.user_memory_enabled and user_ids:
        memories_block = await get_memories_prompt_block(db_path, user_ids)

    memory_section = f"\n{memories_block}\n" if memories_block else ""

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        chat_history=chat_history,
        memory_section=memory_section,
        original_text=original_text,
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key,
    }
    payload = {
        "model": GEMINI_MODEL,
        "input": prompt,
        "tools": [{"type": "google_search"}],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GEMINI_API_URL, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()

        try:
            model_output = next(
                s for s in data["steps"] if s.get("type") == "model_output"
            )
            content_block = model_output["content"][0]
            raw_text = content_block["text"]
            annotations = content_block.get("annotations", [])
            reply_text, parse_mode = _format_with_citations(raw_text, annotations)
        except (KeyError, IndexError, StopIteration, TypeError):
            logger.error("ai_truth_check: unexpected Gemini response shape: %s", data)
            reply_text = MESSAGES["error_generic"]
            parse_mode = None

        await update.message.reply_text(
            reply_text, parse_mode=parse_mode, disable_notification=True
        )

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
