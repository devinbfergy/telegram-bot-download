import logging
import os
from pathlib import Path

from telegram import Message
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from app.config.settings import AppSettings, TELEGRAM_FILE_LIMIT_MB
from app.config.strings import MESSAGES
from app.core.exceptions import ExtractionFailed, SizeLimitExceeded
from app.media.detectors import (
    is_slideshow,
    is_youtube_shorts_url,
    is_instagram_reel_url,
)
from app.media.gallery_dl import download_and_send_with_gallery_dl
from app.media.inspection import detect_frozen_frames
from app.media.ytdlp_profiles import PROFILES
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.concurrency import run_blocking
from app.utils.filesystem import create_temp_dir, safe_cleanup

logger = logging.getLogger(__name__)


class Downloader:
    def __init__(self, settings: AppSettings, status_messenger: StatusMessenger):
        self.settings = settings
        self.status_messenger = status_messenger

    async def download_and_send_media(self, url: str, message: Message) -> None:
        """
        Downloads a video from a URL using yt-dlp, providing status updates to the user,
        and sends the final video file back.
        """
        temp_dir = create_temp_dir()
        video_path: Path | None = None

        try:
            is_shorts = is_youtube_shorts_url(url)
            is_instagram = is_instagram_reel_url(url)

            if is_shorts:
                profile_name = "shorts"
            elif is_instagram:
                profile_name = "instagram"
            else:
                profile_name = "default"

            ydl_opts = PROFILES[profile_name]()

            if is_shorts:
                logger.info(
                    f"YouTube Shorts detected: {url}, using '{profile_name}' profile"
                )
            elif is_instagram:
                logger.info(
                    f"Instagram reel detected: {url}, using '{profile_name}' profile"
                )
            else:
                logger.debug(f"Using '{profile_name}' profile for: {url}")

            # The template from ytdlp_profiles.py is just a filename, not a path
            # We need to join it with our temp_dir
            # Save the template string before yt-dlp modifies it
            outtmpl_str = str(temp_dir / os.path.basename(ydl_opts["outtmpl"]))
            ydl_opts["outtmpl"] = outtmpl_str

            await self.status_messenger.edit_message(MESSAGES["downloading"])

            # Run yt-dlp in a thread to avoid blocking
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
                    video_path = sorted(
                        found_files, key=lambda p: p.stat().st_size, reverse=True
                    )[0]
                    logger.debug(f"Found video file by searching: {video_path}")
                else:
                    raise FileNotFoundError(f"Downloaded file not found in {temp_dir}")

            # --- Post-download checks ---

            # Check for frozen frames
            if detect_frozen_frames(video_path):
                logger.warning(f"Frozen frame video detected: {video_path}")
                await self.status_messenger.edit_message(MESSAGES["frozen_frame_retry"])
                safe_cleanup(video_path)

                fallback_opts = PROFILES["fallback"]()
                fallback_outtmpl_str = str(
                    temp_dir / os.path.basename(fallback_opts["outtmpl"])
                )
                fallback_opts["outtmpl"] = fallback_outtmpl_str
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

                if detect_frozen_frames(video_path):
                    await self.status_messenger.edit_message(
                        MESSAGES["frozen_frame_failed"]
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
            with video_path.open("rb") as video_file:
                await message.reply_video(
                    video=video_file,
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
            await self.status_messenger.edit_message(
                MESSAGES["video_too_large"].format(
                    file_size_mb=file_size_mb, limit_mb=TELEGRAM_FILE_LIMIT_MB
                )
            )
        except FileNotFoundError as fnf:
            logger.error(f"Downloaded file not found for {url}: {fnf}")
            await self.status_messenger.edit_message(MESSAGES["error_generic"])
        except Exception as e:
            logger.error(
                f"An unexpected error occurred for URL {url}: {e}", exc_info=True
            )
            if "Message to delete not found" not in str(e):
                await self.status_messenger.edit_message(MESSAGES["error_generic"])
        finally:
            safe_cleanup(temp_dir)

    def _run_ytdlp_download(self, url: str, ydl_opts: dict) -> dict | None:
        """Wrapper to run yt-dlp download in a sync context."""
        with YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
            return ydl.extract_info(url, download=True)  # type: ignore[return-value]
