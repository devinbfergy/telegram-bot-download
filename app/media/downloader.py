import logging
import os
from pathlib import Path

from telegram import Message
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from app.config.settings import TELEGRAM_FILE_LIMIT_MB, AppSettings
from app.config.strings import MESSAGES
from app.core.exceptions import ExtractionFailed, SizeLimitExceeded
from app.media.detectors import (
    is_instagram_url,
    is_slideshow,
    is_tiktok_url,
    is_youtube_shorts_url,
)
from app.media.gallery_dl import (
    download_and_send_with_gallery_dl,
    load_instagram_headers,
    resolve_instagram_cookiefile,
)
from app.media.inspection import detect_frozen_frames
from app.media.ytdlp_profiles import PROFILES
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.concurrency import run_blocking
from app.utils.database import record_download_issue
from app.utils.filesystem import create_temp_dir, safe_cleanup
from app.utils.validation import summarize_description, truncate_caption

logger = logging.getLogger(__name__)


class Downloader:
    def __init__(self, settings: AppSettings, status_messenger: StatusMessenger):
        self.settings = settings
        self.status_messenger = status_messenger

    async def download_and_send_media(
        self, url: str, message: Message, profile_name: str | None = None
    ) -> None:
        """
        Downloads a video from a URL using yt-dlp, providing status updates to the user,
        and sends the final video file back.

        Args:
            url: The URL to download media from.
            message: The Telegram message to reply to.
            profile_name: Optional profile name to use. If not provided, auto-detected.
        """
        temp_dir = create_temp_dir()
        video_path: Path | None = None

        try:
            # Auto-detect profile if not provided
            if profile_name is None:
                is_shorts = is_youtube_shorts_url(url)
                is_instagram = is_instagram_url(url)

                if is_shorts:
                    profile_name = "shorts"
                elif is_instagram:
                    profile_name = "instagram"
                elif is_tiktok_url(url):
                    profile_name = "tiktok"
                else:
                    profile_name = "default"

            ydl_opts = PROFILES[profile_name]()
            ydl_opts["socket_timeout"] = self.settings.timeouts["yt_dlp"]

            logger.info(f"Using '{profile_name}' profile for: {url}")

            # Attach Instagram credentials (mounted cookies.txt or sessionid env)
            instagram_cookiefile: str | None = None
            if is_instagram_url(url):
                instagram_cookiefile = resolve_instagram_cookiefile(
                    self.settings, temp_dir
                )
                if instagram_cookiefile:
                    ydl_opts["cookiefile"] = instagram_cookiefile
                    ig_headers = load_instagram_headers(self.settings)
                    if ig_headers:
                        ydl_opts["http_headers"] = {
                            **ydl_opts.get("http_headers", {}),
                            **ig_headers,
                        }
                    logger.info(
                        "Using Instagram cookie file for yt-dlp: %s",
                        instagram_cookiefile,
                    )
                else:
                    logger.warning(
                        "Instagram URL but no credentials configured "
                        "(INSTAGRAM_COOKIE_FILE / INSTAGRAM_SESSIONID); download will likely fail"
                    )

            # The template from ytdlp_profiles.py is just a filename, not a path
            # We need to join it with our temp_dir
            # Save the template string before yt-dlp modifies it
            outtmpl_str = str(temp_dir / os.path.basename(ydl_opts["outtmpl"]))
            ydl_opts["outtmpl"] = outtmpl_str

            await self.status_messenger.edit_message(MESSAGES["downloading"])

            # Run yt-dlp in a thread to avoid blocking
            try:
                info_dict = await run_blocking(self._run_ytdlp_download, url, ydl_opts)
            except (ExtractionFailed, YtDlpDownloadError):
                if not instagram_cookiefile:
                    raise
                # Stale/rejected login can fail worse than anonymous access
                logger.warning(
                    "yt-dlp failed with Instagram cookies for %s; retrying without",
                    url,
                )
                ydl_opts.pop("cookiefile", None)
                instagram_cookiefile = None
                info_dict = await run_blocking(self._run_ytdlp_download, url, ydl_opts)

            if not info_dict:
                raise ExtractionFailed("yt-dlp did not return info_dict.")

            # If it's a slideshow, delegate to gallery-dl
            if is_slideshow(info_dict):
                await self.status_messenger.edit_message(MESSAGES["slideshow_detected"])
                await download_and_send_with_gallery_dl(
                    url,
                    message,
                    self.status_messenger,
                    self.settings,
                    purpose="slideshow",
                )
                return

            # Find the downloaded file in the temp directory
            # Try to reconstruct the path from the saved template string
            video_path = None
            try:
                video_path = Path(outtmpl_str % {"id": info_dict["id"], "ext": "mp4"})
            except (TypeError, KeyError) as e:
                # Template formatting failed, we'll search for the file instead
                logger.debug(f"Could not reconstruct path from template: {e}")

            # Search for the output file if reconstruction failed or file doesn't exist
            if not video_path or not video_path.exists():
                found_files = list(temp_dir.glob("*.mp4"))
                if not found_files:
                    found_files = list(temp_dir.glob("*.*"))  # any extension

                if found_files:
                    video_path = max(found_files, key=lambda p: p.stat().st_size)
                    logger.debug(f"Found video file by searching: {video_path}")
                else:
                    raise FileNotFoundError(f"Downloaded file not found in {temp_dir}")

            # --- Post-download checks ---

            # Check for frozen frames off the event loop.
            if await run_blocking(detect_frozen_frames, video_path):
                logger.warning(f"Frozen frame video detected: {video_path}")
                await self.status_messenger.edit_message(MESSAGES["frozen_frame_retry"])
                safe_cleanup(video_path)

                fallback_opts = PROFILES["fallback"]()
                fallback_opts["socket_timeout"] = self.settings.timeouts["yt_dlp"]
                fallback_outtmpl_str = str(
                    temp_dir / os.path.basename(fallback_opts["outtmpl"])
                )
                fallback_opts["outtmpl"] = fallback_outtmpl_str
                if instagram_cookiefile:
                    fallback_opts["cookiefile"] = instagram_cookiefile
                info_dict = await run_blocking(
                    self._run_ytdlp_download, url, fallback_opts
                )

                if not info_dict:
                    raise ExtractionFailed(
                        "Fallback download did not return info_dict."
                    )

                # Find the fallback downloaded file using the saved template
                video_path = None
                try:
                    video_path = Path(
                        fallback_outtmpl_str % {"id": info_dict["id"], "ext": "mp4"}
                    )
                except (TypeError, KeyError) as e:
                    logger.debug(
                        f"Could not reconstruct fallback path from template: {e}"
                    )

                if not video_path or not video_path.exists():
                    found_files = list(temp_dir.glob("*.mp4"))
                    if found_files:
                        video_path = found_files[0]
                        logger.debug(
                            f"Found fallback video file by searching: {video_path}"
                        )
                    else:
                        raise ExtractionFailed(
                            "Fallback download also failed to produce a file."
                        )

                if await run_blocking(detect_frozen_frames, video_path):
                    logger.warning(
                        f"yt-dlp fallback produced a frozen video for {url}. Trying gallery-dl as fallback."
                    )
                    safe_cleanup(video_path)
                    await download_and_send_with_gallery_dl(
                        url,
                        message,
                        self.status_messenger,
                        self.settings,
                        purpose="fallback",
                    )
                    return

            # Check file size
            if video_path.stat().st_size > self.settings.telegram_max_video_size:
                file_size_mb = video_path.stat().st_size / (1024 * 1024)
                raise SizeLimitExceeded(
                    f"Video file size ({file_size_mb:.2f}MB) exceeds Telegram limit ({TELEGRAM_FILE_LIMIT_MB}MB)"
                )

            # --- Uploading ---
            await self.status_messenger.edit_message(MESSAGES["uploading"])

            # Extract caption from video description or title
            description = info_dict.get("description") or info_dict.get("title")
            summarized = summarize_description(description)
            caption = truncate_caption(summarized)

            with video_path.open("rb") as video_file:
                await message.reply_video(
                    video=video_file,
                    caption=caption if caption else None,
                    supports_streaming=True,
                    read_timeout=self.settings.telegram_read_timeout,
                    write_timeout=self.settings.telegram_write_timeout,
                    disable_notification=True,
                )

            await self.status_messenger.delete_status_message()

        except YtDlpDownloadError as de:
            logger.warning(
                f"yt-dlp failed for {url}: {de}. Trying gallery-dl as fallback."
            )
            await download_and_send_with_gallery_dl(
                url, message, self.status_messenger, self.settings, purpose="fallback"
            )
        except ExtractionFailed as ef:
            logger.warning(
                f"Extraction failed for {url}: {ef}. Trying gallery-dl as fallback."
            )
            await download_and_send_with_gallery_dl(
                url, message, self.status_messenger, self.settings, purpose="fallback"
            )
        except SizeLimitExceeded as sle:
            logger.warning(f"File size limit exceeded for {url}: {sle}")
            file_size_mb = (
                video_path.stat().st_size / (1024 * 1024) if video_path else 0
            )
            await self.status_messenger.show_terminal_error(
                MESSAGES["video_too_large"].format(
                    file_size_mb=file_size_mb, limit_mb=TELEGRAM_FILE_LIMIT_MB
                )
            )
            await self._safe_record_issue(
                message,
                url,
                "failed",
                f"Video size ({file_size_mb:.1f}MB) exceeds Telegram limit ({TELEGRAM_FILE_LIMIT_MB}MB)",
            )
        except FileNotFoundError as fnf:
            logger.error(f"Downloaded file not found for {url}: {fnf}")
            await self.status_messenger.show_terminal_error(MESSAGES["error_generic"])
            await self._safe_record_issue(
                message, url, "failed", f"Downloaded file not found: {fnf}"
            )
        except Exception as e:
            logger.exception("An unexpected error occurred for URL %s", url)
            if "Message to delete not found" not in str(e):
                await self.status_messenger.show_terminal_error(
                    MESSAGES["error_generic"]
                )
            await self._safe_record_issue(message, url, "failed", str(e)[:150])
        finally:
            safe_cleanup(temp_dir)

    async def _safe_record_issue(
        self,
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
                db_path=str(self.settings.db_path),
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
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to record download issue: {exc}")

    def _run_ytdlp_download(self, url: str, ydl_opts: dict) -> dict | None:
        """Wrapper to run yt-dlp download in a sync context."""
        opts = dict(ydl_opts)
        if "impersonate" in opts and isinstance(opts["impersonate"], str):
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget

                opts["impersonate"] = ImpersonateTarget.from_str(opts["impersonate"])
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Could not convert impersonate string {opts['impersonate']!r} to ImpersonateTarget: {e}"
                )
                opts.pop("impersonate", None)

        try:
            with YoutubeDL(opts) as ydl:  # type: ignore[arg-type]
                return ydl.extract_info(url, download=True)  # type: ignore[return-value]
        except YtDlpDownloadError:
            raise
        except Exception as e:
            logger.warning(
                f"yt-dlp encountered an error during download for {url}: {e}"
            )
            raise ExtractionFailed(f"yt-dlp failed: {e}") from e
