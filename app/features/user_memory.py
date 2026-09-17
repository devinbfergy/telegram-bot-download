"""
User Memory & Profiling Feature.

Maintains a long-term memory of users who interact with the bot in SQLite.
A periodic background job takes the last day of messages for all active users
and calls Gemini Flash to summarize and update each user's memory.
When someone mentions @gork, these memories are injected into the prompt
to produce personalized, context-aware responses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
from telegram.ext import ContextTypes

from app.utils.database import (
    StoredMessage,
    get_messages_for_last_day,
    get_user_memories,
    get_user_memory,
    set_user_memory,
)

if TYPE_CHECKING:
    from app.config.settings import AppSettings

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_MODEL = "gemini-2.5-flash"

MEMORY_SYNTHESIS_PROMPT = """\
You are an intelligent memory system for a Telegram chat bot called Gork.
Your job is to maintain a concise, vivid, and helpful profile/memory about the user '{name}' (username: {username}, user_id: {user_id}).

{existing_memory_section}

Here are the messages sent by this user in the chat over the last {hours:.0f} hours:
{recent_messages}

Instructions:
1. Synthesize and update the memory profile for this person by combining their existing memory with what they talked about today.
2. Structure the memory concisely (3 to 5 brief bullet points) covering:
   - Profile & Personality: who they are, communication style, humor, and general vibe in the group.
   - Favorite Things & Preferences: their hobbies, passions, likes/dislikes, favorite tech, music, food, or games.
   - Recent Topics & Focus: what they've recently been talking about, working on, sharing, or discussing lately.
3. Be specific and grounded in what they actually said. Do not invent details.
4. Keep it concise (under 120 words total).
5. If the new messages don't add any new useful knowledge, preserve the existing memory.
6. Return ONLY the updated memory text. Do not wrap in conversational preamble, quotes, or markdown code blocks.
"""


def format_user_messages(messages: list[StoredMessage]) -> str:
    """Format a list of stored messages for the Gemini prompt."""
    if not messages:
        return "(no messages)"
    lines: list[str] = []
    for msg in messages:
        lines.append(f"- {msg.message_text}")
    return "\n".join(lines)


async def call_gemini_for_memory(prompt: str, settings: AppSettings) -> str | None:
    """Call Gemini Flash API to generate or update user memory."""
    if not settings.gemini_api_key:
        logger.warning("user_memory: GEMINI_API_KEY is not set")
        return None

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key,
    }
    payload = {
        "model": GEMINI_MODEL,
        "input": prompt,
    }

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                GEMINI_API_URL,
                headers=headers,
                json=payload,
            ) as resp,
        ):
            resp.raise_for_status()
            data = await resp.json()

        # Handle `/interactions` shape
        if "steps" in data:
            model_output = next(
                s for s in data["steps"] if s.get("type") == "model_output"
            )
            content_block = model_output["content"][0]
            return content_block.get("text", "").strip()

        # Handle standard `generateContent` shape fallback
        if "candidates" in data:
            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()

        logger.error("user_memory: unexpected response shape from Gemini: %s", data)
        return None

    except aiohttp.ClientError:
        logger.exception("user_memory: Gemini request failed")
        return None
    except Exception:
        logger.exception("user_memory: unexpected error calling Gemini")
        return None


async def update_user_memory_from_messages(
    user_id: int,
    username: str | None,
    first_name: str | None,
    messages: list[StoredMessage],
    settings: AppSettings,
    hours: float = 24.0,
) -> str | None:
    """
    Synthesize and persist memory for a single user given their messages from the last day.
    """
    if not messages:
        return None

    db_path = str(settings.db_path)
    existing_record = await get_user_memory(db_path, user_id)

    if existing_record and existing_record.memory.strip():
        existing_memory_section = (
            f"Current existing memory for this user:\n{existing_record.memory.strip()}"
        )
    else:
        existing_memory_section = (
            "This is a new user with no previous memory recorded."
        )

    display_name = first_name or username or f"User {user_id}"
    prompt = MEMORY_SYNTHESIS_PROMPT.format(
        name=display_name,
        username=f"@{username}" if username else "unknown",
        user_id=user_id,
        existing_memory_section=existing_memory_section,
        hours=hours,
        recent_messages=format_user_messages(messages),
    )

    new_memory = await call_gemini_for_memory(prompt, settings)
    if new_memory:
        await set_user_memory(
            db_path=db_path,
            user_id=user_id,
            username=username,
            first_name=first_name,
            memory=new_memory,
        )
        logger.info(
            "user_memory: updated memory for user_id=%s (%s)", user_id, display_name
        )
        return new_memory

    return None


async def update_all_user_memories(
    settings: AppSettings,
    hours: float | None = None,
) -> dict[str, int]:
    """
    Take messages from the last day, group by user, and use Gemini to update memories.

    Returns a summary dictionary with counts of updated users.
    """
    if hours is None:
        hours = settings.user_memory_window_hours

    if not settings.gemini_api_key:
        logger.warning(
            "user_memory: GEMINI_API_KEY is not configured; skipping memory update"
        )
        return {"updated": 0, "total_users": 0}

    db_path = str(settings.db_path)
    recent_messages = await get_messages_for_last_day(db_path, hours=hours)

    user_messages: dict[int, list[StoredMessage]] = {}
    user_info: dict[int, tuple[str | None, str | None]] = {}

    for msg in recent_messages:
        if msg.user_id is None:
            continue
        user_messages.setdefault(msg.user_id, []).append(msg)
        curr_u, curr_f = user_info.get(msg.user_id, (None, None))
        user_info[msg.user_id] = (
            msg.username or curr_u,
            msg.first_name or curr_f,
        )

    updated_count = 0
    for uid, msgs in user_messages.items():
        uname, fname = user_info.get(uid, (None, None))
        result = await update_user_memory_from_messages(
            user_id=uid,
            username=uname,
            first_name=fname,
            messages=msgs,
            settings=settings,
            hours=hours,
        )
        if result:
            updated_count += 1

    logger.info(
        "user_memory: batch update completed (%d/%d users updated)",
        updated_count,
        len(user_messages),
    )
    return {"updated": updated_count, "total_users": len(user_messages)}


async def user_memory_cron_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled PTB JobQueue callback."""
    logger.info("user_memory: scheduled job triggered")
    app_settings = context.application.settings.get("app_settings")
    if not app_settings or not app_settings.user_memory_enabled:
        logger.info("user_memory: feature disabled or no settings, skipping")
        return

    try:
        stats = await update_all_user_memories(app_settings)
        logger.info("user_memory: scheduled job finished: %s", stats)
    except Exception:
        logger.exception("user_memory: scheduled job failed")


async def get_memories_prompt_block(
    db_path: str,
    user_ids: list[int] | set[int],
) -> str:
    """
    Retrieve stored memories for given user IDs and format into a prompt context section.
    """
    try:
        clean_ids = [
            uid
            for uid in user_ids
            if isinstance(uid, int) and not isinstance(uid, bool)
        ]
        if not clean_ids:
            return ""

        memories = await get_user_memories(db_path, clean_ids)
        if not memories:
            return ""

        lines = ["User Memories & Context (use this to personalize tone and answers):"]
        for mem in memories.values():
            if not mem.memory or not mem.memory.strip():
                continue
            name = mem.first_name or mem.username or f"User {mem.user_id}"
            handle = f" (@{mem.username})" if mem.username and mem.first_name else ""
            lines.append(f"- {name}{handle}: {mem.memory.strip()}")

        if len(lines) == 1:
            return ""

        return "\n".join(lines)
    except Exception:
        logger.exception("user_memory: could not load memories prompt block")
        return ""
