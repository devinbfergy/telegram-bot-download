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
from telegram import Update
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
Your job is to maintain a memory profile of ONE SPECIFIC PERSON: '{name}' (username: {username}, user_id: {user_id}) in this chat.

CRITICAL RULES TO AVOID MIXING UP USERS:
1. FOCUS EXCLUSIVELY ON {name}: Only extract facts, personal preferences, and personality traits that {name} explicitly reveals about *themselves*.
2. DO NOT ATTRIBUTE GROUP CHATTER OR EVENTS TO THIS PERSON:
   - If the group is discussing an upcoming event, trip, draft, game, or purchase, DO NOT list it as {name}'s personal passion or favorite thing unless {name} explicitly and personally states that they love it.
   - Merely participating in group conversation or asking logistic questions (like packing, times, costs) is NOT a personal hobby.
3. DO NOT CONFUSE OTHER PEOPLE WITH {name}: If {name} talks to or about someone else (e.g. mentions Amanda, Devin, Leighton, Joe, etc.), those are OTHER people's lives and actions, NEVER {name}'s.
4. DO NOT GUESS OR BORROW DETAILS: If {name} only made brief chat comments and revealed no real personal hobbies, favorites, or unique traits, simply write "None explicitly mentioned yet" for those sections. Never fabricate or borrow interests from other chat members.

{existing_memory_section}

Here are the messages sent ONLY by {name} in this chat over the last {hours:.0f} hours:
{recent_messages}

Output format:
- Personality & Vibe: (1-2 sentences on {name}'s communication style and humor, e.g. dry, sarcastic, practical, brief)
- Personal Favorites & Hobbies: (Specific things {name} explicitly confirmed liking about themselves, or "None explicitly mentioned yet")
- Recent Topics: (1 sentence on themes {name} personally talked about)

Keep it under 75 words. Ground every detail strictly in {name}'s actual words. Return ONLY the text above.
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
    chat_id: int = 0,
) -> str | None:
    """
    Synthesize and persist memory for a single user given their messages from the last day.
    """
    if not messages:
        return None

    db_path = str(settings.db_path)
    existing_record = await get_user_memory(db_path, user_id, chat_id=chat_id)

    if existing_record and existing_record.memory.strip():
        existing_memory_section = (
            f"Current existing memory for this user in this chat:\n{existing_record.memory.strip()}"
        )
    else:
        existing_memory_section = (
            "This is a new user with no previous memory recorded in this chat."
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
            chat_id=chat_id,
        )
        logger.info(
            "user_memory: updated memory for user_id=%s (%s) in chat=%s",
            user_id,
            display_name,
            chat_id,
        )
        return new_memory

    return None


async def update_all_user_memories(
    settings: AppSettings,
    hours: float | None = None,
) -> dict[str, int]:
    """
    Take messages from the last day, group by (chat_id, user_id), and use Gemini to update memories.

    Returns a summary dictionary with counts of updated user-chat profiles.
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

    user_messages: dict[tuple[int, int], list[StoredMessage]] = {}
    user_info: dict[tuple[int, int], tuple[str | None, str | None]] = {}

    for msg in recent_messages:
        if msg.user_id is None:
            continue
        key = (msg.chat_id or 0, msg.user_id)
        user_messages.setdefault(key, []).append(msg)
        curr_u, curr_f = user_info.get(key, (None, None))
        user_info[key] = (
            msg.username or curr_u,
            msg.first_name or curr_f,
        )

    updated_count = 0
    for (cid, uid), msgs in user_messages.items():
        uname, fname = user_info.get((cid, uid), (None, None))
        result = await update_user_memory_from_messages(
            user_id=uid,
            username=uname,
            first_name=fname,
            messages=msgs,
            settings=settings,
            hours=hours,
            chat_id=cid,
        )
        if result:
            updated_count += 1

    logger.info(
        "user_memory: batch update completed (%d/%d profiles updated)",
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
    chat_id: int | None = None,
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

        memories = await get_user_memories(db_path, clean_ids, chat_id=chat_id)
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


async def show_user_memory(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    settings: AppSettings,
) -> None:
    """
    Spits out a quick tidbit about the stored memory for a specific user.
    If replying to someone, targets the replied user; otherwise targets the sender.
    """
    if not update.message:
        return

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
    else:
        target_user = update.message.from_user

    if not target_user:
        return

    name = target_user.first_name or (
        f"@{target_user.username}" if target_user.username else "you"
    )
    db_path = str(settings.db_path)
    chat_id = update.effective_chat.id if update.effective_chat else 0
    mem = await get_user_memory(db_path, target_user.id, chat_id=chat_id)
    if not mem or not mem.memory or not mem.memory.strip():
        # Fall back to any memory for this user across chats if not found in current chat
        mem = await get_user_memory(db_path, target_user.id)

    if not mem or not mem.memory or not mem.memory.strip():
        await update.message.reply_text(
            f"I don't have any memories stored for {name} yet. Chat a bit more and I'll start taking notes.",
            disable_notification=True,
        )
        return

    memory_text = mem.memory.strip()

    # If Gemini is configured, ask for a quick witty recap
    if settings.gemini_api_key:
        tidbit_prompt = (
            f"You are Gork, a slightly sarcastic, dry, but warm-hearted bot in a group chat of friends.\n"
            f"Someone asked to see what memories you have on '{name}'.\n\n"
            f"Here is the memory file on {name}:\n{memory_text}\n\n"
            "Instructions:\n"
            "1. Give a quick, witty 1-2 sentence tidbit summarizing what you remember about them.\n"
            "2. Then present their key traits/facts in 2-3 brief bullet points.\n"
            "3. Keep the total response under 80 words. Stay dry and quippy."
        )
        tidbit = await call_gemini_for_memory(tidbit_prompt, settings)
        if tidbit:
            await update.message.reply_text(tidbit, disable_notification=True)
            return

    # Fallback if Gemini is not available or failed
    reply = f"🧠 Here's what I have on {name}:\n\n{memory_text}"
    await update.message.reply_text(reply, disable_notification=True)
