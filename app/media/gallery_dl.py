import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from telegram import InputMediaPhoto, InputMediaVideo, Message

from app.config.settings import AppSettings
from app.config.strings import MESSAGES
from app.media.detectors import is_instagram_url
from app.media.slideshow import create_slideshow_from_media
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.concurrency import run_blocking
from app.utils.database import record_download_issue
from app.utils.filesystem import create_temp_dir
from app.utils.validation import summarize_description, truncate_caption

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
        # yt-dlp saves the cookie jar back on exit; the mounted secrets dir is
        # read-only, so hand out a private writable copy instead.
        copy = temp_dir / "instagram_cookies.txt"
        shutil.copyfile(cookie_file, copy)
        return str(copy)

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


def load_instagram_headers(settings: AppSettings) -> dict[str, str]:
    """
    Real Chrome headers captured on the host by refresh_session.py (stored beside the
    cookie file). Using the same User-Agent / client hints as the browser that owns the
    session avoids Instagram's "new device" suspicion. Empty when unavailable.
    """
    if not settings.instagram_cookie_file:
        return {}
    path = Path(settings.instagram_cookie_file).with_name("instagram_session.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


async def _safe_record_issue(
    settings: AppSettings,
    message: Message,
    url: str,
    issue_type: str,
    error_message: str | None = None,
    total_items: int | None = None,
    downloaded_items: int | None = None,
) -> None:
    try:
        chat_id = getattr(message, "chat_id", 0) or 0
        from_user = getattr(message, "from_user", None)
        await record_download_issue(
            db_path=str(settings.db_path),
            chat_id=chat_id,
            url=url,
            issue_type=issue_type,
            error_message=error_message,
            total_items=total_items,
            downloaded_items=downloaded_items,
            user_id=getattr(from_user, "id", None),
            username=getattr(from_user, "username", None),
            first_name=getattr(from_user, "first_name", None),
        )
    except Exception as exc:
        logger.warning(f"Failed to record download issue: {exc}")


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
    2. Inspects downloaded files and metadata to identify media and album counts.
    3. If images and audio are found and purpose is 'slideshow', a slideshow video is created.
    4. Otherwise, sends all media (images, videos, or mixed) as single items or media groups,
       chunking albums into batches of up to 10 items.
    5. Checks if the album was complete, recording any failed or incomplete downloads.

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
        user_agent = (
            load_instagram_headers(settings).get("user-agent", "")
            if is_instagram_url(url)
            else ""
        )
        try:
            await run_blocking(
                _run_gallery_dl_subprocess,
                url,
                temp_dir,
                cookie_file or "",
                user_agent,
            )
        except subprocess.CalledProcessError:
            if not cookie_file:
                raise
            logger.warning(
                "gallery-dl failed with cookies for %s; retrying without", url
            )
            await run_blocking(_run_gallery_dl_subprocess, url, temp_dir, "")

        all_files = list(temp_dir.rglob("*.*"))
        if not all_files:
            await status_messenger.edit_message(MESSAGES["gallery_dl_no_media"])
            await _safe_record_issue(
                settings,
                message,
                url,
                issue_type="failed",
                error_message="No media found in URL",
            )
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

        # Extract caption and album metadata from gallery-dl JSON
        caption, expected_count, file_num_map = _inspect_gallery_dl_metadata(temp_dir)

        # 1. If images + audio and purpose is slideshow (e.g. TikTok slideshow), create video
        if images and audios and not videos and purpose == "slideshow":
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
                        read_timeout=settings.telegram_read_timeout,
                        write_timeout=settings.telegram_write_timeout,
                        disable_notification=True,
                    )
                await status_messenger.delete_status_message()
                return True

        # 2. General photo album / video / mixed-media handling
        def _get_item_order(p: Path) -> tuple[int, str]:
            num = file_num_map.get(p.name, file_num_map.get(p.stem, 999999))
            return (num, p.name)

        media_items = sorted(images + videos, key=_get_item_order)

        if not media_items:
            await status_messenger.edit_message(
                MESSAGES["gallery_dl_no_suitable_media"]
            )
            await _safe_record_issue(
                settings,
                message,
                url,
                issue_type="failed",
                error_message="No suitable images or videos found",
            )
            return False

        # Filter out videos exceeding size limit
        valid_media: list[Path] = []
        for item in media_items:
            if item.suffix.lower() in settings.media_video_extensions:
                if item.stat().st_size > settings.telegram_max_video_size:
                    logger.warning(
                        f"Video file {item} exceeds size limit ({item.stat().st_size} bytes), skipping"
                    )
                    continue
            valid_media.append(item)

        if not valid_media:
            await status_messenger.edit_message(
                MESSAGES["gallery_dl_no_suitable_media"]
            )
            await _safe_record_issue(
                settings,
                message,
                url,
                issue_type="failed",
                error_message="All downloaded media exceeded Telegram size limit",
            )
            return False

        # Send single media item
        if len(valid_media) == 1:
            single = valid_media[0]
            if single.suffix.lower() in settings.media_video_extensions:
                await status_messenger.edit_message(
                    MESSAGES["gallery_dl_uploading_video"]
                )
                with single.open("rb") as vf:
                    await message.reply_video(
                        video=vf,
                        caption=caption if caption else None,
                        supports_streaming=True,
                        read_timeout=settings.telegram_read_timeout,
                        write_timeout=settings.telegram_write_timeout,
                        disable_notification=True,
                    )
            else:
                await status_messenger.edit_message(
                    MESSAGES["gallery_dl_sending_images"]
                )
                with single.open("rb") as pf:
                    await message.reply_photo(
                        photo=pf,
                        caption=caption if caption else None,
                        read_timeout=settings.telegram_read_timeout,
                        write_timeout=settings.telegram_write_timeout,
                        disable_notification=True,
                    )

            # Check if this single download was supposed to be a larger album
            if expected_count is not None and expected_count > 1:
                logger.warning(
                    f"Incomplete album for {url}: downloaded 1 of {expected_count} items"
                )
                await _safe_record_issue(
                    settings=settings,
                    message=message,
                    url=url,
                    issue_type="incomplete_album",
                    error_message=f"Only downloaded 1 of {expected_count} photos/items in album",
                    total_items=expected_count,
                    downloaded_items=1,
                )

            await status_messenger.delete_status_message()
            return True

        # Send multi-item album / media group (batches of up to telegram_max_media_group_size)
        await status_messenger.edit_message(MESSAGES["gallery_dl_sending_images"])
        chunk_size = settings.telegram_max_media_group_size
        chunks = [
            valid_media[i : i + chunk_size]
            for i in range(0, len(valid_media), chunk_size)
        ]

        for chunk_idx, chunk in enumerate(chunks):
            is_first_chunk = chunk_idx == 0
            if len(chunk) >= 2:
                media_group = []
                opened_files = []
                try:
                    for item_idx, item in enumerate(chunk):
                        item_caption = (
                            caption
                            if (is_first_chunk and item_idx == 0 and caption)
                            else None
                        )
                        fh = item.open("rb")
                        opened_files.append(fh)
                        if item.suffix.lower() in settings.media_video_extensions:
                            media_group.append(
                                InputMediaVideo(
                                    media=fh,
                                    caption=item_caption,
                                    supports_streaming=True,
                                )
                            )
                        else:
                            media_group.append(
                                InputMediaPhoto(media=fh, caption=item_caption)
                            )

                    await message.reply_media_group(
                        media=media_group,
                        read_timeout=settings.telegram_read_timeout,
                        write_timeout=settings.telegram_write_timeout,
                        disable_notification=True,
                    )
                finally:
                    for fh in opened_files:
                        try:
                            fh.close()
                        except Exception:
                            pass
            else:
                # Single item leftover in the last chunk
                single = chunk[0]
                item_caption = caption if (is_first_chunk and caption) else None
                if single.suffix.lower() in settings.media_video_extensions:
                    with single.open("rb") as vf:
                        await message.reply_video(
                            video=vf,
                            caption=item_caption,
                            supports_streaming=True,
                            read_timeout=settings.telegram_read_timeout,
                            write_timeout=settings.telegram_write_timeout,
                            disable_notification=True,
                        )
                else:
                    with single.open("rb") as pf:
                        await message.reply_photo(
                            photo=pf,
                            caption=item_caption,
                            read_timeout=settings.telegram_read_timeout,
                            write_timeout=settings.telegram_write_timeout,
                            disable_notification=True,
                        )

        # Check if fewer items were downloaded than the album actually contained
        total_downloaded = len(valid_media)
        if expected_count is not None and total_downloaded < expected_count:
            logger.warning(
                f"Incomplete album for {url}: downloaded {total_downloaded} of {expected_count} items"
            )
            await _safe_record_issue(
                settings=settings,
                message=message,
                url=url,
                issue_type="incomplete_album",
                error_message=f"Only downloaded {total_downloaded} of {expected_count} photos/items in album",
                total_items=expected_count,
                downloaded_items=total_downloaded,
            )

        await status_messenger.delete_status_message()
        return True

    except FileNotFoundError as fnf:
        logger.error(f"gallery-dl binary not found: {fnf}")
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error="gallery-dl not installed")
        )
        await _safe_record_issue(
            settings,
            message,
            url,
            issue_type="failed",
            error_message="gallery-dl binary not found",
        )
        return False
    except subprocess.CalledProcessError as cpe:
        logger.error(f"gallery-dl subprocess failed for {url}: {cpe}", exc_info=True)
        err_text = cpe.stderr.decode("utf-8", errors="ignore") if cpe.stderr else ""
        if is_instagram_url(url) and (
            "login" in err_text.lower() or "401" in err_text or "403" in err_text
        ):
            await status_messenger.edit_message(MESSAGES["instagram_login_required"])
            reason = "Instagram login required / cookies expired"
        else:
            await status_messenger.edit_message(
                MESSAGES["gallery_dl_error"].format(error="Download failed")
            )
            reason = (
                f"Download failed: {err_text[:120]}" if err_text else "Download failed"
            )
        await _safe_record_issue(
            settings,
            message,
            url,
            issue_type="failed",
            error_message=reason,
        )
        return False
    except subprocess.TimeoutExpired as te:
        logger.error(f"gallery-dl timed out for {url}: {te}")
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error="Download timed out")
        )
        await _safe_record_issue(
            settings,
            message,
            url,
            issue_type="failed",
            error_message="Download timed out (300s)",
        )
        return False
    except Exception as e:
        logger.error(f"gallery-dl failed for {url}: {e}", exc_info=True)
        await status_messenger.edit_message(
            MESSAGES["gallery_dl_error"].format(error=e)
        )
        await _safe_record_issue(
            settings,
            message,
            url,
            issue_type="failed",
            error_message=str(e)[:150],
        )
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_gallery_dl_subprocess(
    url: str, temp_dir: Path, cookie_file: str = "", user_agent: str = ""
) -> None:
    """Helper to run gallery-dl in a subprocess with metadata extraction."""
    try:
        cmd = ["gallery-dl", "-d", str(temp_dir), "--write-info-json"]

        if cookie_file and is_instagram_url(url):
            cmd.extend(["--cookies", cookie_file])
            if user_agent:
                cmd.extend(["-o", f"user-agent={user_agent}"])

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


def _inspect_gallery_dl_metadata(
    temp_dir: Path,
) -> tuple[str, int | None, dict[str, int]]:
    """
    Extracts caption, expected total item count, and item order index map from gallery-dl JSON files.
    """
    json_files = list(temp_dir.rglob("*.json"))
    caption = ""
    expected_count: int | None = None
    file_num_map: dict[str, int] = {}

    for json_file in json_files:
        try:
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not caption:
                description = (
                    data.get("description")
                    or data.get("content")
                    or data.get("caption")
                    or data.get("title")
                    or ""
                )
                if description:
                    summarized = summarize_description(description)
                    caption = truncate_caption(summarized)

            # Check for count indicators across different extractors
            count = (
                data.get("count")
                or data.get("post_item_count")
                or data.get("playlist_count")
            )
            if isinstance(count, int) and count > 0:
                expected_count = max(expected_count or 0, count)

            num = data.get("num")
            if isinstance(num, int) and num > 0:
                expected_count = max(expected_count or 0, num)
                stem = json_file.stem
                file_num_map[stem] = num
                file_num_map[json_file.name] = num
                file_num_map[Path(stem).stem] = num
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Failed to parse gallery-dl JSON {json_file}: {e}")
            continue

    return caption, expected_count, file_num_map


def _extract_caption_from_gallery_dl(temp_dir: Path) -> str:
    """Extract caption/description from gallery-dl info JSON files."""
    caption, _, _ = _inspect_gallery_dl_metadata(temp_dir)
    return caption
