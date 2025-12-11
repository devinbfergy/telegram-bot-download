import asyncio
import logging
import os
from pathlib import Path

from telegram import Message
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.config.settings import AppSettings, TELEGRAM_FILE_LIMIT_MB
from app.config.strings import MESSAGES
from app.media.detectors import is_slideshow, is_youtube_shorts_url
from app.media.gallery_dl import download_and_send_with_gallery_dl
from app.media.inspection import detect_frozen_frames
from app.media.ytdlp_profiles import PROFILES
from app.telegram_bot.status_messenger import StatusMessenger
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
            profile_name = "shorts" if is_youtube_shorts_url(url) else "default"
            ydl_opts = PROFILES[profile_name]()
            # The template from ytdlp_profiles.py is just a filename, not a path
            # We need to join it with our temp_dir
            ydl_opts["outtmpl"] = str(temp_dir / os.path.basename(ydl_opts["outtmpl"]))


            await self.status_messenger.edit_message(MESSAGES["downloading"])

            # Run yt-dlp in a thread to avoid blocking
            info_dict = await asyncio.to_thread(self._run_ytdlp_download, url, ydl_opts)

            if not info_dict:
                raise DownloadError("yt-dlp did not return info_dict.")

            # If it's a slideshow, delegate to gallery-dl
            if is_slideshow(info_dict):
                await self.status_messenger.edit_message(MESSAGES["slideshow_detected"])
                await download_and_send_with_gallery_dl(
                    url, message, self.status_messenger, self.settings, purpose="slideshow"
                )
                return

            # Reconstruct the path from the info_dict and the template
            video_path = Path(ydl_opts["outtmpl"] % {"id": info_dict["id"], "ext": "mp4"}) # Assume mp4 due to merge_output_format

            # A more robust way to find the output file
            if not video_path.exists():
                found_files = list(temp_dir.glob(f"*.mp4"))
                if not found_files:
                    found_files = list(temp_dir.glob(f"*.*")) # any extension

                if found_files:
                    video_path = sorted(found_files, key=lambda p: p.stat().st_size, reverse=True)[0]
                else:
                    raise FileNotFoundError(f"Downloaded file not found in {temp_dir}")


            # --- Post-download checks ---

            # Check for frozen frames
            if detect_frozen_frames(video_path):
                logger.warning(f"Frozen frame video detected: {video_path}")
                await self.status_messenger.edit_message(
                    MESSAGES["frozen_frame_retry"]
                )
                safe_cleanup(video_path)

                fallback_opts = PROFILES["fallback"]()
                fallback_opts["outtmpl"] = str(temp_dir / os.path.basename(fallback_opts["outtmpl"]))
                info_dict = await asyncio.to_thread(self._run_ytdlp_download, url, fallback_opts)

                video_path = Path(fallback_opts["outtmpl"] % {"id": info_dict["id"], "ext": "mp4"})
                if not video_path.exists():
                    found_files = list(temp_dir.glob(f"*.mp4"))
                    if found_files:
                        video_path = found_files[0]
                    else:
                        raise FileNotFoundError("Fallback download also failed to produce a file.")

                if detect_frozen_frames(video_path):
                    await self.status_messenger.edit_message(
                        MESSAGES["frozen_frame_failed"]
                    )
                    return

            # Check file size
            if video_path.stat().st_size > self.settings.telegram_max_video_size:
                file_size_mb = video_path.stat().st_size / (1024 * 1024)
                await self.status_messenger.edit_message(
                    MESSAGES["video_too_large"].format(
                        file_size_mb=file_size_mb,
                        limit_mb=TELEGRAM_FILE_LIMIT_MB
                    )
                )
                return

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

        except DownloadError as de:
            logger.warning(f"yt-dlp failed for {url}: {de}. Trying gallery-dl as fallback.")
            await download_and_send_with_gallery_dl(
                url, message, self.status_messenger, self.settings, purpose="fallback"
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred for URL {url}: {e}", exc_info=True)
            if "Message to delete not found" not in str(e):
                await self.status_messenger.edit_message(
                    MESSAGES["error_generic"]
                )
        finally:
            safe_cleanup(temp_dir)

    def _run_ytdlp_download(self, url: str, ydl_opts: dict) -> dict | None:
        """Wrapper to run yt-dlp download in a sync context."""
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)
