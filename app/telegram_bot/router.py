from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import (
    ApplicationHandlerStop,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.features.user_memory import user_memory_cron_job
from app.telegram_bot import handlers
from app.utils.validation import is_chat_allowed

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)


def register(application: Application) -> Application:
    """
    Register all handlers with the Telegram application.

    Handler groups:
      Group 0  – primary routing (first match wins within the group).
      Group 2  – passive message logger (runs for every text message,
                 never blocks other handlers).

    Args:
        application: The Telegram Application instance.

    Returns:
        The application with handlers registered.
    """
    logger.info("Registering handlers...")

    # ------------------------------------------------------------------ #
    # Group -1 – global allowlist guard (drops updates from unallowed chats)#
    # ------------------------------------------------------------------ #
    application.add_handler(TypeHandler(Update, check_chat_allowlist), group=-1)
    logger.info("Registered check_chat_allowlist guard (group -1)")

    # ------------------------------------------------------------------ #
    # Group 0 – primary handlers, ordered most-specific → least-specific  #
    # ------------------------------------------------------------------ #

    # /start command
    application.add_handler(CommandHandler("start", handlers.start))
    logger.info("Registered /start command handler")

    # "bad bot" reply → reprocess the download
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & filters.Regex(r"(?i)bad\s+bot"),
            handlers.handle_bad_bot_reply,
        )
    )
    logger.info("Registered handle_bad_bot_reply handler")

    # "good bot" — group 0 so it wins over the catch-all and does not also
    # run handle_message (python-telegram-bot runs every handler group).
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)good\s+bot"),
            handlers.handle_good_bot_reply,
        )
    )
    logger.info("Registered handle_good_bot_reply handler")

    # "@gork is this real" reply → Gemini fact-check
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.REPLY
            & filters.Regex(r"(?i)@gork\s+is\s+this\s+real"),
            handlers.handle_gork_is_this_real,
        )
    )
    logger.info("Registered handle_gork_is_this_real handler")

    # "@gork open (an) issue" → GitHub issue via Gemini
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)@gork\s+open\s+(an\s+)?issue"),
            handlers.handle_gork_open_issue,
        )
    )
    logger.info("Registered handle_gork_open_issue handler")

    # Messages FROM @guys_being_dudes_bot → Gemini context-aware reply
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.User(username="guys_being_dudes_bot"),
            handlers.handle_guys_being_dudes_mention,
        )
    )
    logger.info("Registered handle_guys_being_dudes_mention handler")

    # "@gork memory" or "@guys_being_dudes_bot memory" → show user memories
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)(@gork|@guys_being_dudes_bot)\s+memory"),
            handlers.handle_user_memory,
        )
    )
    logger.info("Registered handle_user_memory handler")

    # Generic @gork or @guys_being_dudes_bot mention (anything not caught above)
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)(@gork|@guys_being_dudes_bot)"),
            handlers.handle_mention,
        )
    )
    logger.info(
        "Registered handle_mention (@gork / @guys_being_dudes_bot generic) handler"
    )

    # Catch-all URL downloader
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )
    logger.info("Registered handle_message handler")

    # ------------------------------------------------------------------ #
    # Group 2 – passive message logger (never stops propagation)          #
    # ------------------------------------------------------------------ #
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handlers.log_message_to_db,
        ),
        group=2,
    )
    logger.info("Registered log_message_to_db handler (group 2)")

    # ------------------------------------------------------------------ #
    # Background jobs (JobQueue)                                         #
    # ------------------------------------------------------------------ #
    register_jobs(application)

    logger.info(f"Total handler groups: {len(application.handlers)}")
    for group_id, handler_list in application.handlers.items():
        logger.info(f"  Group {group_id}: {len(handler_list)} handlers")
        for i, h in enumerate(handler_list):
            handler_name = (
                getattr(h.callback, "__name__", str(h.callback))
                if hasattr(h, "callback")
                else str(h)
            )
            logger.info(f"    [{i}] {type(h).__name__}: {handler_name}")

    return application


def register_jobs(application: Application) -> None:
    """Register scheduled background jobs if a JobQueue is configured."""
    job_queue = getattr(application, "job_queue", None)
    if job_queue is None:
        logger.debug("No JobQueue configured; skipping background job registration")
        return

    app_settings = getattr(application, "settings", {}).get("app_settings")
    enabled = (
        getattr(app_settings, "user_memory_enabled", True)
        if app_settings is not None
        else True
    )
    if not enabled:
        logger.info("User memory feature disabled; skipping scheduled job")
        return

    interval_seconds = (
        app_settings.user_memory_interval_hours * 3600
        if app_settings is not None
        else 24.0 * 3600
    )
    job_queue.run_repeating(
        callback=user_memory_cron_job,
        interval=interval_seconds,
        first=60.0,
        name="user_memory_update",
    )
    logger.info("Registered user_memory_cron_job (interval=%.1fs)", interval_seconds)


async def check_chat_allowlist(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Drop updates from chats that are not in the allowlist.
    Only allows:
    1. Chats in settings.allowed_chat_ids.
    2. Direct messages (DMs) with the creator/admin (@megadevx).
    """
    settings = getattr(context.application, "settings", {}).get("app_settings")
    if settings and not is_chat_allowed(update, settings):
        chat_id = (
            update.effective_chat.id if getattr(update, "effective_chat", None) else "unknown"
        )
        logger.debug(
            "check_chat_allowlist: dropping update from non-allowed chat %s", chat_id
        )
        raise ApplicationHandlerStop
