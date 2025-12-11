from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from app.config.settings import AppSettings


# Placeholder for reprocessing previously failed / low quality downloads
async def reprocess_bad_bot(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """Handle 'bad bot' replies to reprocess failed downloads."""
    # TODO: Extract original URL from replied message
    # TODO: Load prior artifacts, attempt improved download
    pass
