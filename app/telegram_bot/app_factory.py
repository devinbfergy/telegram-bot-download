from __future__ import annotations
from dataclasses import dataclass
from app.config.settings import load_config
from app.core.logging import setup_logging, get_logger
from app.telegram_bot.router import register
from telegram.ext import ApplicationBuilder  # type: ignore

log = get_logger(__name__)

def create_application():
    cfg = load_config()
    setup_logging(cfg.log_level, cfg.log_json)
    if not cfg.api_token:
        raise RuntimeError("API_TOKEN not set in environment")
    app = ApplicationBuilder().token(cfg.api_token).build()
    register(app)
    log.info("application.created real_app=yes")
    return app
