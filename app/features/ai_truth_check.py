import html as html_module
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

SYSTEM_PROMPT_TEMPLATE = """You are Gork, a fact-checking bot with the energy of someone who has seen too much and is mildly annoyed by it. You tell the truth, you use the internet to back it up, and you do it with a little attitude.

Rules:
- Be concise and direct — 2-4 sentences max.
- Sassy but not mean. Helpful but not boring.
- Never start with "Well," or "Oh," — be more creative than that.
- Don't repeat the question back. Just answer it.
- Use your Google Search tool to verify claims. Cite what you found.
- If it's opinion or unverifiable, make a dry observation about it.
- If it's obviously false, feel free to be a little dramatic about it.

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


def _format_with_citations(text: str, annotations: list[dict]) -> tuple[str, str | None]:
    """
    Insert inline [n] citation markers into the model's text using the
    start_index/end_index offsets from each url_citation annotation, then
    append a numbered sources list as HTML links.

    Returns (formatted_text, parse_mode): parse_mode is "HTML" when citations
    are present, None otherwise (plain text — no HTML escaping needed).
    """
    url_citations = [a for a in annotations if a.get("type") == "url_citation"]
    if not url_citations:
        return text, None

    # Assign citation numbers in first-appearance order (by start_index).
    seen_urls: dict[str, int] = {}
    for a in sorted(url_citations, key=lambda x: x.get("start_index", 0)):
        url = a.get("url", "")
        if url and url not in seen_urls:
            seen_urls[url] = len(seen_urls) + 1

    # Insert "[n]" markers from the end of the string backwards so earlier
    # indices stay valid after each insertion.
    result = text
    for a in sorted(url_citations, key=lambda x: x.get("end_index", 0), reverse=True):
        url = a.get("url", "")
        num = seen_urls.get(url)
        if num is None:
            continue
        end = min(a.get("end_index", len(result)), len(result))
        result = result[:end] + f"[{num}]" + result[end:]

    # HTML-escape the text (square brackets are safe; only & < > " need escaping).
    escaped = html_module.escape(result)

    # Build the numbered sources footer.
    sources = "\n\n<b>Sources:</b>"
    for url, num in sorted(seen_urls.items(), key=lambda kv: kv[1]):
        title = next(
            (a.get("title") or url for a in url_citations if a.get("url") == url),
            url,
        )
        sources += f'\n{num}. <a href="{html_module.escape(url)}">{html_module.escape(title)}</a>'

    return escaped + sources, "HTML"


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
            async with session.post(GEMINI_API_URL, headers=headers, json=payload) as response:
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

        await update.message.reply_text(reply_text, parse_mode=parse_mode, disable_notification=True)

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
