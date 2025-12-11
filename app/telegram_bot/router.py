from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import CommandHandler, MessageHandler, filters

from app.telegram_bot import handlers

if TYPE_CHECKING:
    from telegram.ext import Application


def register(application: Application) -> Application:
    """
    Register all handlers with the Telegram application.

    Args:
        application: The Telegram Application instance.

    Returns:
        The application with handlers registered.
    """
    # Command handlers
    application.add_handler(CommandHandler("start", handlers.start))

    # Reply message handlers - check for specific patterns in replies
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & ~filters.COMMAND,
            handlers.handle_bad_bot_reply,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.REPLY & ~filters.COMMAND,
            handlers.handle_gork_is_this_real,
        )
    )

    # General message handler - processes URLs
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )

    return application
