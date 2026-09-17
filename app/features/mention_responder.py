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
from app.features.user_memory import get_memories_prompt_block
from app.utils.database import StoredMessage, get_recent_messages

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
You are Gork (also known as @guys_being_dudes_bot), a bot in a private group chat of friends.
Have a dry, sarcastic, and quippy tone — don't be overly cheerful, eager-to-please, or sycophantic. \
Still be warm at heart: never be mean, cruel, or dunk on people, and don't make fun of the person \
talking to you. Deliver witty, dry banter with some sarcasm, but remain genuinely helpful and \
give real answers in 2-3 sentences. Never introduce yourself unprompted. If you don't have context, \
ask a dry, quick clarifying question instead of guessing. You can use Google Search to look things up — \
and you should, especially for anything factual or current events.

About your capabilities and how people call and talk to you:
- Direct Chat & Mentions: People talk to you by tagging @gork or @guys_being_dudes_bot. You chat about anything, answer questions, joke around, or give advice.
- Addressing People: Always address or refer to the person you are speaking with by their real first name (e.g. "Devin" or "Ryan"), not their Telegram @handle or username. Respond directly to the person who sent the current incoming message.
- Media Downloader: Whenever users drop links to videos, reels, shorts, or photos (TikTok, Instagram, YouTube, Twitter/X, Reddit, Facebook, etc.), you automatically download and send the media into the chat.
- Fact Checking: When someone replies to a message with "@gork is this real", you fact-check the claim using Google Search and deliver a direct verdict.
- GitHub Issue Creation: When someone says "@gork open issue" or "@gork open an issue", you summarize recent conversation context and create an issue on the project's GitHub repo.
- Video Fixes: If a video is frozen or glitches and someone replies "bad bot", you reprocess and re-encode the video for Telegram.
- Good Bot Praise: When someone says "good bot", they're appreciating you.
- User Memory & Profiling: You have a persistent memory of each person in the chat (their personality, favorite things, hobbies, and recent topics). Use these memories to make your responses personal and natural, without robotically announcing that you looked them up.
{memory_section}
Recent chat history (last 10 minutes):
{chat_history}

Now respond to the following message. Stay in character.\
"""


def _format_history(messages: list[StoredMessage]) -> str:
    if not messages:
        return "(no recent messages — you're flying blind)"
    lines: list[str] = []
    for msg in messages:
        if msg.first_name and msg.username:
            display_name = f"{msg.first_name} (@{msg.username})"
        elif msg.first_name:
            display_name = msg.first_name
        elif msg.username:
            display_name = f"@{msg.username}"
        else:
            display_name = "unknown"
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

    user_ids: set[int] = set()
    if update.message.from_user and update.message.from_user.id:
        user_ids.add(update.message.from_user.id)
    for msg in recent:
        if msg.user_id:
            user_ids.add(msg.user_id)

    memories_block = ""
    if settings.user_memory_enabled and user_ids:
        memories_block = await get_memories_prompt_block(db_path, user_ids)

    memory_section = f"\n{memories_block}\n" if memories_block else ""

    sender = update.message.from_user
    sender_first = (
        sender.first_name
        if sender and isinstance(getattr(sender, "first_name", None), str)
        else None
    )
    sender_last = (
        sender.last_name
        if sender and isinstance(getattr(sender, "last_name", None), str)
        else None
    )
    sender_uname = (
        sender.username
        if sender and isinstance(getattr(sender, "username", None), str)
        else None
    )
    name_parts = [p for p in (sender_first, sender_last) if p]
    sender_full = " ".join(name_parts)
    if sender_full and sender_uname:
        sender_display = f"{sender_full} (@{sender_uname})"
    elif sender_full:
        sender_display = sender_full
    elif sender_uname:
        sender_display = f"@{sender_uname}"
    else:
        sender_display = "someone"

    preferred_name = sender_first or (f"@{sender_uname}" if sender_uname else "friend")

    reply_context = ""
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        replied_user = update.message.reply_to_message.from_user
        r_first = (
            replied_user.first_name
            if isinstance(getattr(replied_user, "first_name", None), str)
            else None
        )
        r_last = (
            replied_user.last_name
            if isinstance(getattr(replied_user, "last_name", None), str)
            else None
        )
        r_uname = (
            replied_user.username
            if isinstance(getattr(replied_user, "username", None), str)
            else None
        )
        r_parts = [p for p in (r_first, r_last) if p]
        r_full = " ".join(r_parts)
        if r_full and r_uname:
            r_display = f"{r_full} (@{r_uname})"
        elif r_full:
            r_display = r_full
        elif r_uname:
            r_display = f"@{r_uname}"
        else:
            r_display = "someone"
        raw_r_text = (
            update.message.reply_to_message.text
            or update.message.reply_to_message.caption
            or ""
        )
        r_text = raw_r_text if isinstance(raw_r_text, str) else ""
        if r_text:
            reply_context = f"\n(Replying to {r_display}: \"{r_text}\")"
        else:
            reply_context = f"\n(Replying to {r_display})"

    full_prompt = _SYSTEM_PROMPT.format(
        chat_history=history_block,
        memory_section=memory_section,
    )
    if trigger_text:
        full_prompt += (
            f"\n\nCurrent incoming message from {sender_display} "
            f"(address them as '{preferred_name}'):{reply_context}\n"
            f"\"{trigger_text}\""
        )

    api_url = GEMINI_API_URL
    payload = {
        "model": GEMINI_MODEL,
        "input": full_prompt,
        "tools": [{"type": "google_search"}],
    }

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=payload,
            ) as resp,
        ):
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

    except aiohttp.ClientError:
        logger.exception("mention_responder: Gemini request failed")
        await update.message.reply_text(
            MESSAGES["error_ai_api_request_failed"],
            disable_notification=True,
        )
    except Exception:
        logger.exception("mention_responder: unexpected error")
        await update.message.reply_text(
            MESSAGES["error_generic"],
            disable_notification=True,
        )
