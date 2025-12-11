from __future__ import annotations
from telegram.ext import CommandHandler, MessageHandler, filters  # type: ignore
from app.telegram_bot import handlers

def register(application):  # noqa: ANN001
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    return application
