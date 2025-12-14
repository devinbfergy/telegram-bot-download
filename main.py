import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.core.logging import setup_logging
from app.telegram_bot.app_factory import create_app

logger = logging.getLogger(__name__)


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all incoming updates for debugging."""
    logger.info(f"=== RECEIVED UPDATE {update.update_id} ===")
    if update.message:
        logger.info(f"  Message ID: {update.message.message_id}")
        logger.info(f"  Chat ID: {update.message.chat_id}")
        logger.info(
            f"  From: {update.message.from_user.username if update.message.from_user else 'unknown'}"
        )
        logger.info(f"  Text: {update.message.text}")
    elif update.edited_message:
        logger.info(f"  Edited message: {update.edited_message.text}")
    elif update.channel_post:
        logger.info(f"  Channel post")
    else:
        logger.info(f"  Other update type: {type(update)}")
    logger.info("=== END UPDATE ===")


def main() -> None:
    """Application entrypoint."""
    # 1. Load settings
    settings = AppSettings()

    # 2. Setup logging
    setup_logging(settings.log_level, settings.log_json)
    logger.info("Application starting...")

    # 3. Validate API token
    if not settings.api_token or settings.api_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.critical(
            "!!! PLEASE SET YOUR API_TOKEN IN .env OR ENVIRONMENT VARIABLE !!!"
        )
        return

    # 4. Create and run the Telegram application
    app = create_app(settings)

    # Add a handler that logs ALL updates (group=-1 means it runs before other handlers)
    from telegram.ext import TypeHandler

    app.add_handler(TypeHandler(Update, log_all_updates), group=-1)
    logger.info("Added debug update logger")

    logger.info("Telegram application created. Starting polling...")
    app.run_polling()
    logger.info("Application shutting down.")


if __name__ == "__main__":
    main()
