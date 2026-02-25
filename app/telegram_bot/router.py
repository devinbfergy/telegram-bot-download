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

    Args:
        application: The Telegram Application instance.

    Returns:
        The application with handlers registered.
    """
    logger.info("Registering handlers...")

    # Command handlers
    application.add_handler(CommandHandler("start", handlers.start))
    logger.info("Registered /start command handler")

    # Reply message handlers - check for specific patterns in replies
    # Use Regex filters to only match when the specific text is present
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & filters.Regex(r"(?i)bad\s+bot"),
            handlers.handle_bad_bot_reply,
        )
    )
    logger.info("Registered handle_bad_bot_reply handler")

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & filters.REPLY
            & filters.Regex(r"(?i)@gork\s+is\s+this\s+real"),
            handlers.handle_gork_is_this_real,
        )
    )
    logger.info("Registered handle_gork_is_this_real handler")

    # GitHub issue handler - @gork open issue / @gork open an issue
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)@gork\s+open\s+(an\s+)?issue"),
            handlers.handle_gork_open_issue,
        )
    )
    logger.info("Registered handle_gork_open_issue handler")

    # General message handler - processes URLs
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )
    logger.info("Registered handle_message handler")

    # Good bot handler - handles "good bot" from @McClintock96 (doesn't require reply)
    # Put in group 1 so it always runs even if handle_message processes the message
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"(?i)good\s+bot"),
            handlers.handle_good_bot_reply,
        ),
        group=1,
    )

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
