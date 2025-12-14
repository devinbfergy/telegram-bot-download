from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from app.config.settings import AppSettings

from app.config.strings import MESSAGES
from app.media.downloader import Downloader
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.validation import extract_url

logger = logging.getLogger(__name__)


async def reprocess_bad_bot(
    update: Update, context: ContextTypes.DEFAULT_TYPE, settings: AppSettings
) -> None:
    """
    Handle 'bad bot' replies to reprocess failed downloads.

    Extracts the URL from the replied message and reprocesses it
    with the "telegram" profile for better quality.
    """
    if not update.message or not update.message.reply_to_message:
        logger.warning("reprocess_bad_bot: No message or no reply, returning")
        return

    replied_message = update.message.reply_to_message

    # Extract text from the replied message
    text = replied_message.text or replied_message.caption
    if not text:
        logger.warning("reprocess_bad_bot: No text in replied message")
        await update.message.reply_text(MESSAGES["reprocessing_no_url"])
        return

    # Extract URL from the text
    url = extract_url(text)
    if not url:
        logger.warning(f"reprocess_bad_bot: No URL found in text: {text}")
        await update.message.reply_text(MESSAGES["reprocessing_no_url"])
        return

    logger.info(f"reprocess_bad_bot: Reprocessing URL with telegram profile: {url}")

    # Create status messenger for this reprocessing request
    # Note: effective_chat should always be present for message updates
    message_thread_id = update.message.message_thread_id if update.message else None
    status_messenger = StatusMessenger(
        bot=context.bot,
        chat_id=update.effective_chat.id,  # type: ignore[union-attr]
        settings=settings,
        message_thread_id=message_thread_id,
    )

    # Send initial status message
    await status_messenger.send_message(MESSAGES["reprocessing"])

    # Create downloader and process with telegram profile
    downloader = Downloader(settings, status_messenger)

    try:
        await downloader.download_and_send_media(
            url, replied_message, profile_name="telegram"
        )
    except Exception as e:
        logger.error(f"reprocess_bad_bot: Error reprocessing {url}: {e}", exc_info=True)
        await status_messenger.edit_message(MESSAGES["error_generic"])
    finally:
        # Ensure the status message is deleted
        if status_messenger.has_active_message():
            await status_messenger.delete_status_message()
