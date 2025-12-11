import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.features.ai_truth_check import ai_truth_check
from app.features.reprocess_bad_bot import reprocess_bad_bot
from app.media.downloader import Downloader
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.validation import extract_url
from app.media.detectors import is_image_url, is_tiktok_photo_url, is_video_url

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_html(MESSAGES["start"], disable_notification=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles incoming text messages, extracts a URL, and attempts to download the media.
    """
    if not update.message or not update.message.text:
        return

    url = extract_url(update.message.text)
    if not url:
        return

    settings: AppSettings = context.application.settings["app_settings"]
    status_messenger = StatusMessenger(
        bot=context.bot, chat_id=update.effective_chat.id, settings=settings
    )
    downloader = Downloader(settings, status_messenger)

    try:
        if is_tiktok_photo_url(url):
            await status_messenger.send_message(MESSAGES["tiktok_photo_alert"])
        elif is_video_url(url) or is_image_url(url) or "snapchat" in url or "facebook" in url:
            await status_messenger.send_message(MESSAGES["link_alert"])
        else:
            logger.info(f"Ignoring non-media URL: {url}")
            return

        await downloader.download_and_send_media(url, update.message)

    except Exception as e:
        # The downloader class should handle its own errors and status messages.
        # This is a final fallback.
        logger.error(f"Unhandled error in handle_message for URL {url}: {e}", exc_info=True)
        await status_messenger.send_message(MESSAGES["error_generic"])
    finally:
        # Ensure the status message is deleted unless an error occurred that we want to persist
        if status_messenger.has_active_message():
             await status_messenger.delete_status_message()


async def handle_bad_bot_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles replies with 'bad bot' to a video message.
    """
    if not update.message or not update.message.reply_to_message:
        return

    if "bad bot" not in update.message.text.lower():
        return

    settings: AppSettings = context.application.settings["app_settings"]
    await reprocess_bad_bot(update, context, settings)


async def handle_gork_is_this_real(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles replies with '@gork is this real'.
    """
    if not update.message or not update.message.reply_to_message:
        return

    if "@gork is this real" not in update.message.text.lower():
        return

    settings: AppSettings = context.application.settings["app_settings"]
    await ai_truth_check(update, context, settings)
