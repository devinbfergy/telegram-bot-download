from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.settings import load_config
from app.core.logging import get_logger
from app.telegram_bot.router import register
from telegram.ext import ApplicationBuilder

if TYPE_CHECKING:
    from app.config.settings import AppSettings
    from telegram.ext import Application

log = get_logger(__name__)


def create_app(settings: AppSettings | None = None) -> Application:
    """
    Create and configure the Telegram bot application.

    Args:
        settings: Optional AppSettings instance. If None, loads from environment.

    Returns:
        Configured Telegram Application instance.

    Raises:
        RuntimeError: If API_TOKEN is not set.
    """
    if settings is None:
        settings = load_config()

    if not settings.api_token:
        raise RuntimeError("API_TOKEN not set in environment")

    app = ApplicationBuilder().token(settings.api_token).build()

    # Store settings in application for handlers to access
    app.settings = {"app_settings": settings}  # type: ignore[attr-defined]

    register(app)
    log.info("application.created")
    return app
