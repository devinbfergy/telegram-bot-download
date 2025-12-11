import logging

from app.config.settings import AppSettings
from app.core.logging import setup_logging
from app.telegram_bot.app_factory import create_app


def main() -> None:
    """Application entrypoint."""
    # 1. Load settings
    settings = AppSettings()

    # 2. Setup logging
    setup_logging(settings.log_level, settings.log_json)
    logger = logging.getLogger(__name__)
    logger.info("Application starting...")

    # 3. Validate API token
    if not settings.api_token or settings.api_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.critical(
            "!!! PLEASE SET YOUR API_TOKEN IN .env OR ENVIRONMENT VARIABLE !!!"
        )
        return

    # 4. Create and run the Telegram application
    app = create_app(settings)
    logger.info("Telegram application created. Starting polling...")
    app.run_polling()
    logger.info("Application shutting down.")


if __name__ == "__main__":
    main()
