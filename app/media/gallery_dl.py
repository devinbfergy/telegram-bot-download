import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from telegram import InputMediaPhoto, Message

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.media.detectors import is_instagram_url
from app.media.slideshow import create_slideshow_from_media
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.concurrency import run_blocking
from app.utils.filesystem import create_temp_dir
from app.utils.validation import truncate_caption

logger = logging.getLogger(__name__)


def resolve_instagram_cookiefile(settings: AppSettings, temp_dir: Path) -> str | None:
    """
    Resolve a Netscape cookies.txt path for Instagram downloads.

    Precedence:
      1. INSTAGRAM_COOKIE_FILE (kept fresh by scripts/instagram_session/refresh_session.py).
      2. INSTAGRAM_SESSIONID env var, synthesized into a temp cookies.txt.

    Returns None when no credentials are available.
    """
    cookie_file = settings.instagram_cookie_file
    if cookie_file and Path(cookie_file).is_file():
        return cookie_file

    if settings.instagram_sessionid:
        path = temp_dir / "instagram_cookies.txt"
        expiry = int(time.time()) + 365 * 24 * 3600
        path.write_text(
            "# Netscape HTTP Cookie File\n"
            f".instagram.com\tTRUE\t/\tTRUE\t{expiry}\tsessionid\t{settings.instagram_sessionid}\n",
            encoding="utf-8",
        )
        return str(path)

    return None


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
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_processing"].format(purpose=purpose)
        )

        # Run gallery-dl in a separate thread to avoid blocking asyncio loop
        cookie_file = (
            resolve_instagram_cookiefile(settings, temp_dir)
            if is_instagram_url(url)
            else None
        )
        await run_blocking(_run_gallery_dl_subprocess, url, temp_dir, cookie_file or "")

        all_files = list(temp_dir.rglob("*.*"))
        if not all_files:
            await status_messenger.edit_message(MESSAGES["gallery_dl_no_media"])
            return False

        # Categorize files (exclude JSON metadata files)
        videos = [
            f for f in all_files if f.suffix.lower() in settings.media_video_extensions
        ]
        images = [
            f for f in all_files if f.suffix.lower() in settings.media_image_extensions
        ]
        audios = [
            f for f in all_files if f.suffix.lower() in settings.media_audio_extensions
        ]

        # Extract caption from gallery-dl metadata
        caption = _extract_caption_from_gallery_dl(temp_dir)

        # 1. Prioritize sending a video if one is found under the size limit
        if videos:
            chosen_video = min(videos, key=lambda p: p.stat().st_size)
            if chosen_video.stat().st_size <= settings.telegram_max_video_size:
                await status_messenger.edit_message(
                    MESSAGES["gallery_dl_uploading_video"]
                )
                with chosen_video.open("rb") as vf:
                    await message.reply_video(
                        video=vf,
                        caption=caption if caption else None,
                        supports_streaming=True,
                        disable_notification=True,
                    )
                return True

        # 2. If no suitable video, try to create a slideshow
        if images and audios:
            slideshow_path = temp_dir / "slideshow.mp4"
            await status_messenger.edit_message(MESSAGES["slideshow_building"])
            success = await run_blocking(
                create_slideshow_from_media,
                images[: settings.slideshow_max_images],
                audios[0],
                slideshow_path,
            )
            if (
                success
                and slideshow_path.stat().st_size <= settings.telegram_max_video_size
            ):
                await status_messenger.edit_message(
                    MESSAGES["gallery_dl_uploading_slideshow"]
                )
                with slideshow_path.open("rb") as vf:
                    await message.reply_video(
                        video=vf,
                        caption=caption if caption else None,
                        supports_streaming=True,
                        disable_notification=True,
                    )
                return True

        # 3. If no video or slideshow, send images
        if images:
            await status_messenger.edit_message(MESSAGES["gallery_dl_sending_images"])
            # For media groups, caption goes on the first item only
            images_to_send = images[: settings.telegram_max_media_group_size]
            media_group = []
            for i, img in enumerate(images_to_send):
                if i == 0 and caption:
                    media_group.append(InputMediaPhoto(img.open("rb"), caption=caption))
                else:
                    media_group.append(InputMediaPhoto(img.open("rb")))
            await message.reply_media_group(
                media=media_group, disable_notification=True
            )
            for m in media_group:
                m.media.close()  # type: ignore[union-attr]
            return True

        await status_messenger.edit_message(MESSAGES["gallery_dl_no_suitable_media"])
        return False

    except FileNotFoundError as fnf:
        logger.error(f"gallery-dl binary not found: {fnf}")
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error="gallery-dl not installed")
        )
        return False
    except subprocess.CalledProcessError as cpe:
        logger.error(f"gallery-dl subprocess failed for {url}: {cpe}", exc_info=True)
        err_text = cpe.stderr.decode("utf-8", errors="ignore") if cpe.stderr else ""
        if is_instagram_url(url) and (
            "login" in err_text.lower() or "401" in err_text or "403" in err_text
        ):
            await status_messenger.edit_message(MESSAGES["instagram_login_required"])
        else:
            await status_messenger.edit_message(
                MESSAGES["gallery_dl_error"].format(error="Download failed")
            )
        return False
    except subprocess.TimeoutExpired as te:
        logger.error(f"gallery-dl timed out for {url}: {te}")
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error="Download timed out")
        )
        return False
    except Exception as e:
        logger.error(f"gallery-dl failed for {url}: {e}", exc_info=True)
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error=e)
        )
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_gallery_dl_subprocess(url: str, temp_dir: Path, cookie_file: str = "") -> None:
    """Helper to run gallery-dl in a subprocess with metadata extraction."""
    try:
        cmd = ["gallery-dl", "-d", str(temp_dir), "--write-info-json"]

        if cookie_file and is_instagram_url(url):
            cmd.extend(["--cookies", cookie_file])

        cmd.append(url)

        subprocess.run(
            cmd,
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


def _extract_caption_from_gallery_dl(temp_dir: Path) -> str:
    """Extract caption/description from gallery-dl info JSON files."""
    json_files = list(temp_dir.rglob("*.json"))
    if not json_files:
        return ""

    # Try to find description in any of the JSON files
    for json_file in json_files:
        try:
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # gallery-dl uses various field names for description
                description = (
                    data.get("description")
                    or data.get("content")
                    or data.get("caption")
                    or data.get("title")
                    or ""
                )
                if description:
                    return truncate_caption(description)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to parse gallery-dl JSON {json_file}: {e}")
            continue

    return ""
