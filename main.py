import logging

from app.config.settings import AppSettings
from app.core.logging import setup_logging
from app.telegram_bot.app_factory import create_app


def main() -> None:
    """Application entrypoint."""
    # 1. Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application starting...")

    # 2. Load settings
    settings = AppSettings()
    logger.debug("Loaded application settings: %s", settings.model_dump_json(indent=2))

    if settings.telegram_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.critical(
            "!!! PLEASE SET YOUR TELEGRAM BOT TOKEN IN .env OR ENVIRONMENT VARIABLE !!!"
        )
        return

    # 3. Create and run the Telegram application
    app = create_app(settings)
    logger.info("Telegram application created. Starting polling...")
    app.run_polling()
    logger.info("Application shutting down.")


if __name__ == "__main__":
    main()