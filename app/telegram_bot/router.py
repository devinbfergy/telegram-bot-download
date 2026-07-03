from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import CommandHandler, MessageHandler, filters

from app.telegram_bot import handlers

if TYPE_CHECKING:
    from telegram.ext import Application


import logging

logger = logging.getLogger(__name__)


def register(application: Application) -> Application:
    """
    Register all handlers with the Telegram application.

    Handler groups:
      Group 0  – primary routing (first match wins within the group).
      Group 1  – "good bot" (runs independently alongside group 0).
      Group 2  – passive message logger (runs for every text message,
                 never blocks other handlers).

    Args:
        application: The Telegram Application instance.

    Returns:
        The application with handlers registered.
    """
    logger.info("Registering handlers...")

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

    # Generic @gork mention (anything not caught by the specific handlers above)
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)@gork"),
            handlers.handle_mention,
        )
    )
    logger.info("Registered handle_mention (@gork generic) handler")

    # Catch-all URL downloader
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )
    logger.info("Registered handle_message handler")

    # ------------------------------------------------------------------ #
    # Group 1 – "good bot" (always fires, even if group 0 consumed msg)   #
    # ------------------------------------------------------------------ #
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)good\s+bot"),
            handlers.handle_good_bot_reply,
        ),
        group=1,
    )
    logger.info("Registered handle_good_bot_reply handler (group 1)")

    # ------------------------------------------------------------------ #
    # Group 2 – passive message logger (never stops propagation)          #
    # ------------------------------------------------------------------ #
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handlers.log_message_to_db,
        ),
        group=2,
    )
    logger.info("Registered log_message_to_db handler (group 2)")

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
