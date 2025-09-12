import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

from telegram import InputMediaPhoto, Message

from app.config.settings import AppSettings
from app.media.slideshow import create_slideshow_from_media
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.filesystem import create_temp_dir

logger = logging.getLogger(__name__)


async def download_and_send_with_gallery_dl(
    url: str,
    message: Message,
    status_messenger: StatusMessenger,
    settings: AppSettings,
    purpose: str = "media",
) -> bool:
    """
    Downloads media using gallery-dl and sends it to the chat.

    This function orchestrates the following steps:
    1. Runs gallery-dl to download media into a temporary directory.
    2. Inspects the downloaded files to decide on the best course of action.
    3. If a suitable video is found, it's sent.
    4. If images and audio are found, a slideshow is created and sent.
    5. If only images are found, they are sent as a media group.

    Args:
        url: The URL to download from.
        message: The original Telegram message to reply to.
        status_messenger: The StatusMessenger for sending updates.
        settings: The application settings.
        purpose: A string describing the purpose of the download (for logging).

    Returns:
        True if media was successfully sent, False otherwise.
    """
    temp_dir = create_temp_dir()
    try:
        await status_messenger.edit_message(f"🧩 Using gallery-dl for {purpose}...")

        # Run gallery-dl in a separate thread to avoid blocking asyncio loop
        await asyncio.to_thread(_run_gallery_dl_subprocess, url, temp_dir)

        all_files = list(temp_dir.rglob("*.*"))
        if not all_files:
            await status_messenger.edit_message("❌ No media found via gallery-dl.")
            return False

        # Categorize files
        videos = [f for f in all_files if f.suffix.lower() in settings.media_video_extensions]
        images = [f for f in all_files if f.suffix.lower() in settings.media_image_extensions]
        audios = [f for f in all_files if f.suffix.lower() in settings.media_audio_extensions]

        # 1. Prioritize sending a video if one is found under the size limit
        if videos:
            chosen_video = min(videos, key=lambda p: p.stat().st_size)
            if chosen_video.stat().st_size <= settings.telegram_max_video_size:
                await status_messenger.edit_message("⬆️ Uploading video (gallery-dl)...")
                with chosen_video.open("rb") as vf:
                    await message.reply_video(
                        video=vf, supports_streaming=True, disable_notification=True
                    )
                return True

        # 2. If no suitable video, try to create a slideshow
        if images and audios:
            slideshow_path = temp_dir / "slideshow.mp4"
            await status_messenger.edit_message("🛠️ Building slideshow video...")
            success = await asyncio.to_thread(
                create_slideshow_from_media,
                images[:60],  # Limit number of images
                audios[0],
                slideshow_path,
            )
            if success and slideshow_path.stat().st_size <= settings.telegram_max_video_size:
                await status_messenger.edit_message("⬆️ Uploading slideshow...")
                with slideshow_path.open("rb") as vf:
                    await message.reply_video(
                        video=vf, supports_streaming=True, disable_notification=True
                    )
                return True

        # 3. If no video or slideshow, send images
        if images:
            await status_messenger.edit_message("⬆️ Sending images (gallery-dl)...")
            media_group = [InputMediaPhoto(img.open("rb")) for img in images[:10]]
            await message.reply_media_group(media=media_group, disable_notification=True)
            for m in media_group:
                m.media.close()
            return True

        await status_messenger.edit_message("❌ No suitable media found to send.")
        return False

    except Exception as e:
        logger.error(f"gallery-dl failed for {url}: {e}", exc_info=True)
        await status_messenger.edit_message(f"❌ gallery-dl error: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_gallery_dl_subprocess(url: str, temp_dir: Path) -> None:
    """Helper to run gallery-dl in a subprocess."""
    try:
        subprocess.run(
            ["gallery-dl", "-d", str(temp_dir), url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300,
        )
    except FileNotFoundError:
        raise RuntimeError("gallery-dl is not installed or not in PATH.")
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.decode("utf-8", errors="ignore")
        logger.error(f"gallery-dl subprocess failed with output:\n{error_output}")
        raise
