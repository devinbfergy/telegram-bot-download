import logging
import os
import re
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
import aiohttp
import asyncio

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

try:
    import gallery_dl
except ImportError:
    gallery_dl = None

import json, subprocess  # added json and subprocess for new TikTok photo fallback
import uuid, glob, shutil  # added for gallery-dl refactor
import math  # for duration calculations

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Your Telegram Bot Token ---
# It's recommended to use environment variables for security.
TOKEN = os.environ.get("API_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")


def extract_url(text: str) -> str | None:
    """Extracts the first URL from a given text using a regex pattern."""
    url_pattern = r"(https?://[^\s/$.?#].[^\s]*)"
    match = re.search(url_pattern, text)
    return match.group(0) if match else None


def is_youtube_shorts_url(url: str) -> bool:
    """Checks if the URL is a YouTube Shorts link."""
    youtube_pattern = (
        r"(?:https?://)?(?:www\.)?(?:m\.)?"
        r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)"
        r"([a-zA-Z0-9_-]{11})"
    )
    return re.match(youtube_pattern, url) is not None


def is_video_url(url):
    """
    Checks if a URL is a video URL that yt-dlp can actually extract
    metadata from, implying it could potentially be downloaded.
    """
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "simulate": True,
        "skip_download": True,
        "force_generic_extractor": False,
        "no_warnings": True,
        "dump_single_json": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            logger.debug(info)
            if info.get("extractor") == "generic":
                return False
            if "formats" in info and len(info["formats"]) > 0:
                return True
            if "entries" in info and isinstance(info["entries"], list):
                for entry in info["entries"]:
                    if entry and "formats" in entry and len(entry["formats"]) > 0:
                        return True
            if (
                "url" in info
                and isinstance(info["url"], str)
                and (
                    "video" in info["url"]
                    or any(
                        ext in info["url"]
                        for ext in [".mp4", ".mkv", ".webm", ".mov", ".avi"]
                    )
                )
            ):
                return True
            return False
        except DownloadError:
            return False
        except Exception:
            return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_html(
        "<b>Video Downloader Bot is active!</b>\n\n"
        "I will automatically watch for messages containing video links from sites "
        "like YouTube, Instagram, and Facebook, and reply with the downloaded video. "
        "Just send a link in a message!",
        disable_notification=True,
    )


def is_tiktok_photo_url(url: str) -> bool:
    return bool(re.search(r"tiktok\.com/@[^/]+/photo/\d+", url))


def _create_slideshow_video(images, audio_path, output_path, temp_dir):
    """Create an MP4 slideshow video from a list of image paths and an audio file.
    Returns True on success, False otherwise."""
    try:
        # Probe audio duration
        try:
            import subprocess, json
            probe = subprocess.run([
                'ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1', audio_path
            ], capture_output=True, text=True, timeout=15)
            audio_duration = float(probe.stdout.strip()) if probe.returncode == 0 else None
        except Exception:
            audio_duration = None
        if not audio_duration or audio_duration <= 0:
            audio_duration = 2.0 * len(images)
        per_image = audio_duration / len(images)
        # Cap per-image duration between 0.5 and 8 seconds
        per_image = max(0.5, min(8.0, per_image))
        slides_dir = os.path.join(temp_dir, 'slides_norm')
        os.makedirs(slides_dir, exist_ok=True)
        normalized = []
        for idx, img in enumerate(images):
            tgt = os.path.join(slides_dir, f"frame{idx:04d}.jpg")
            if img.lower().endswith(('.jpg','.jpeg')):
                try:
                    import shutil
                    shutil.copyfile(img, tgt)
                except Exception:
                    return False
            else:
                # Convert to jpg via ffmpeg
                try:
                    subprocess.run(['ffmpeg','-y','-v','error','-i', img, tgt], check=True, timeout=30)
                except Exception:
                    return False
            normalized.append(tgt)
        # Frame rate so each frame lasts per_image seconds => fps = 1/per_image
        fps = 1.0 / per_image
        # Build video from frames then mux audio (avoid desync by using -shortest)
        temp_video = os.path.join(temp_dir, 'slideshow_noaudio.mp4')
        cmd_frames = [
            'ffmpeg','-y','-v','error','-framerate', f'{fps:.4f}', '-i', os.path.join(slides_dir,'frame%04d.jpg'),
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart', temp_video
        ]
        try:
            subprocess.run(cmd_frames, check=True, timeout=300)
        except Exception:
            return False
        cmd_mux = [
            'ffmpeg','-y','-v','error','-i', temp_video, '-i', audio_path,
            '-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart', output_path
        ]
        try:
            subprocess.run(cmd_mux, check=True, timeout=300)
        except Exception:
            return False
        return os.path.exists(output_path)
    except Exception:
        return False


async def send_via_gallery_dl(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, processing_message_id: int, purpose: str = "") -> bool:
    """Download media using gallery-dl and send to chat.
    Returns True if something was sent successfully, otherwise False.
    Logic:
      1. Run gallery-dl into unique temp dir.
      2. Collect files (videos first preference if within size limit, else images).
      3. Send media (video or up to 10 images). Delete processing message on success.
    """
    chat_id = update.effective_chat.id
    temp_root = os.path.join("downloads", "gallery_dl")
    os.makedirs(temp_root, exist_ok=True)
    temp_dir = os.path.join(temp_root, str(uuid.uuid4()))
    os.makedirs(temp_dir, exist_ok=True)

    try:
        try:
            await context.bot.edit_message_text(
                f"🧩 Using gallery-dl {('('+purpose+')') if purpose else ''}...",
                chat_id=chat_id,
                message_id=processing_message_id,
            )
        except Exception:
            pass
        # Run gallery-dl (sync) in thread
        def _run_gallery_dl():
            if gallery_dl is not None:
                try:
                    cfg = gallery_dl.config.Config()
                    cfg.set("base-directory", temp_dir)
                    job = gallery_dl.job.Job(url, cfg)
                    job.run()
                    return True
                except Exception:
                    pass
            # Fallback to subprocess if module route failed
            try:
                subprocess.run([
                    "gallery-dl", "-d", temp_dir, url
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=300)
                return True
            except Exception:
                return False
        ok = await asyncio.to_thread(_run_gallery_dl)
        if not ok:
            await context.bot.edit_message_text(
                "❌ gallery-dl failed to process the link.", chat_id=chat_id, message_id=processing_message_id
            )
            return False
        # Collect files
        all_files = [f for f in glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True) if os.path.isfile(f)]
        if not all_files:
            await context.bot.edit_message_text(
                "❌ No media found via gallery-dl.", chat_id=chat_id, message_id=processing_message_id
            )
            return False
        video_exts = (".mp4", ".webm", ".mov", ".mkv", ".avi")
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff")
        videos = [f for f in all_files if f.lower().endswith(video_exts)]
        images = [f for f in all_files if f.lower().endswith(image_exts)]
        audio_exts = ('.mp3','.m4a','.aac','.wav','.ogg','.opus')
        audios = [f for f in all_files if f.lower().endswith(audio_exts)]
        # Prefer first video under 50MB if available
        chosen_video = None
        for v in sorted(videos, key=lambda p: os.path.getsize(p)):
            if os.path.getsize(v) <= 50 * 1024 * 1024:
                chosen_video = v
                break
        if chosen_video:
            try:
                await context.bot.edit_message_text(
                    "⬆️ Uploading video (gallery-dl)...", chat_id=chat_id, message_id=processing_message_id
                )
            except Exception:
                pass
            with open(chosen_video, "rb") as vf:
                await update.message.reply_video(video=vf, supports_streaming=True, disable_notification=True)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
            except Exception:
                pass
            return True
        # Slideshow to video attempt if images + audio and no chosen video
        if images and audios:
            audio_path = sorted(audios, key=lambda p: os.path.getsize(p))[0]
            slideshow_path = os.path.join(temp_dir, 'slideshow.mp4')
            try:
                await context.bot.edit_message_text(
                    "🛠️ Building slideshow video...", chat_id=chat_id, message_id=processing_message_id
                )
            except Exception:
                pass
            ok_build = await asyncio.to_thread(
                _create_slideshow_video, images[:60], audio_path, slideshow_path, temp_dir
            )
            if ok_build and os.path.getsize(slideshow_path) <= 50*1024*1024:
                try:
                    await context.bot.edit_message_text(
                        "⬆️ Uploading slideshow video...", chat_id=chat_id, message_id=processing_message_id
                    )
                except Exception:
                    pass
                try:
                    with open(slideshow_path,'rb') as vf:
                        await update.message.reply_video(video=vf, supports_streaming=True, disable_notification=True)
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
                    except Exception:
                        pass
                    return True
                except Exception:
                    pass  # fall back to images
        # Otherwise send images
        if images:
            try:
                await context.bot.edit_message_text(
                    "⬆️ Sending images (gallery-dl)...", chat_id=chat_id, message_id=processing_message_id
                )
            except Exception:
                pass
            media_group = []
            for img_path in images[:10]:
                try:
                    media_group.append(InputMediaPhoto(open(img_path, "rb")))
                except Exception:
                    continue
            if media_group:
                await update.message.reply_media_group(media=media_group, disable_notification=True)
                for m in media_group:
                    try: m.media.close()
                    except Exception: pass
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
                except Exception:
                    pass
                return True
        await context.bot.edit_message_text(
            "❌ No suitable media (video/images) to send.", chat_id=chat_id, message_id=processing_message_id
        )
        return False
    except Exception as e:
        try:
            await context.bot.edit_message_text(
                f"❌ gallery-dl error: {e}", chat_id=chat_id, message_id=processing_message_id
            )
        except Exception:
            pass
        return False
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


async def _download_and_send_tiktok_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, processing_message_id: int):
    await send_via_gallery_dl(update, context, url, processing_message_id, purpose="tiktok photo")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles incoming text messages, extracts a URL, and attempts to download the video or image.
    """
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    url = extract_url(message_text)

    if url:
        if is_tiktok_photo_url(url):
            processing_message = await update.message.reply_text("🚨‼️ TIKTOK PHOTO ALERT ‼️🚨", disable_notification=True)
            await _download_and_send_tiktok_photo(update, context, url, processing_message.message_id)
            return
        if is_video_url(url):
            processing_message = await update.message.reply_text("🚨‼️ LINK ALERT ‼️🚨", disable_notification=True)
            await download_and_send_video(
                update, context, url, processing_message.message_id
            )
        elif is_image_url(url):
            processing_message = await update.message.reply_text("🚨‼️ IMAGE LINK ALERT ‑️🚨", disable_notification=True)
            await download_and_send_images(
                update, context, url, processing_message.message_id
            )
        elif "snapchat" in url or "facebook" in url:
            processing_message = await update.message.reply_text("🚨‼️ LINK ALERT ‼️🚨", disable_notification=True)
            await download_and_send_video(
                update, context, url, processing_message.message_id
            )


def is_frozen_frame_video(video_path, max_frames=30, threshold=1e-3):
    """
    Checks if the video at video_path is a frozen frame video (all frames are visually identical).
    Only checks up to max_frames for efficiency.
    Returns True if frozen, False otherwise, or None if OpenCV is not available.
    """
    if cv2 is None or np is None:
        logger.warning("OpenCV not installed, skipping frozen frame check.")
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            return None
        prev_frame_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        frame_count = 1
        frozen = True
        while frame_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(prev_frame_gray, frame_gray)
            nonzero = np.count_nonzero(diff)
            if nonzero > threshold * diff.size:
                frozen = False
                break
            frame_count += 1
        cap.release()
        return frozen
    except Exception as e:
        logger.error(f"Error during frozen frame check: {e}")
        return None


async def _handle_slideshow(info_dict, update: Update, context: ContextTypes.DEFAULT_TYPE, processing_message_id: int) -> None:
    """Refactored slideshow handler: delegate to gallery-dl instead of manual assembly."""
    url = info_dict.get("webpage_url") or info_dict.get("original_url") or info_dict.get("url")
    if not url:
        chat_id = update.effective_chat.id
        await context.bot.edit_message_text(
            "❌ Slideshow source URL missing.", chat_id=chat_id, message_id=processing_message_id
        )
        return
    await send_via_gallery_dl(update, context, url, processing_message_id, purpose="slideshow")


def _is_slideshow_info(info_dict) -> bool:
    """Detect if the yt-dlp info dict represents a TikTok/Instagram slideshow (photo mode)."""
    if not isinstance(info_dict, dict):
        return False
    if info_dict.get("_type") == "playlist" and info_dict.get("extractor_key") in ("TikTok", "Instagram"):  # playlist of entries
        entries = info_dict.get("entries") or []
        image_like = 0
        for e in entries:
            if not e:
                continue
            ext = (e.get("ext") or "").lower()
            if ext in ("jpg","jpeg","png","webp"):
                image_like += 1
        return image_like > 0 and image_like == len([e for e in entries if e])
    return False


async def download_and_send_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    processing_message_id: int,
):
    """
    Downloads a video from a URL using yt-dlp, providing status updates to the user,
    and sends the final video file back. It uses different settings for YouTube Shorts.
    If the download fails and the link is an image, tries to download and send images.
    """
    chat_id = update.effective_chat.id
    video_filename = None

    original_ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "noplaylist": True,
        "quiet": False,
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"skip_dash_manifest": True}},
        "postprocessor_args": {
            "ffmpeg_downloader": [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "28",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "faststart",
            ],
        },
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegMetadata",
                "add_chapters": False,
                "add_infojson": False,
                "add_metadata": True,
            },
        ],
    }

    youtube_shorts_opts = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
        "postprocessor_args": [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ],
    }

    fallback_ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s_fallback.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
    }

    if is_youtube_shorts_url(url):
        logger.info(f"YouTube Shorts link detected. Using specific settings for: {url}")
        ydl_opts = youtube_shorts_opts
    else:
        logger.info(f"Standard link detected. Using original settings for: {url}")
        ydl_opts = original_ydl_opts

    try:
        await context.bot.edit_message_text(
            "📥 Downloading...", chat_id=chat_id, message_id=processing_message_id
        )

        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if _is_slideshow_info(info_dict):
                # Use gallery-dl for slideshow instead of manual processing
                await send_via_gallery_dl(update, context, url, processing_message_id, purpose="slideshow")
                return
            video_filename = ydl.prepare_filename(info_dict)

        if not video_filename or not os.path.exists(video_filename):
            raise FileNotFoundError(
                f"Downloaded file not found on disk: {video_filename}"
            )

        frozen_result = is_frozen_frame_video(video_filename)
        if frozen_result is True:
            logger.warning(f"Frozen frame video detected: {video_filename}")
            await context.bot.edit_message_text(
                "⚠️ Detected a frozen frame video. Retrying download with fallback settings...",
                chat_id=chat_id,
                message_id=processing_message_id,
            )
            try:
                os.remove(video_filename)
            except Exception:
                pass
            with YoutubeDL(fallback_ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                video_filename = ydl.prepare_filename(info_dict)
            frozen_result2 = is_frozen_frame_video(video_filename)
            if frozen_result2 is True:
                await context.bot.edit_message_text(
                    "❌ The downloaded video appears to be frozen (all frames identical). This may be a site limitation.",
                    chat_id=chat_id,
                    message_id=processing_message_id,
                )
                return

        file_size_mb = os.path.getsize(video_filename) / (1024 * 1024)
        if file_size_mb > 50:
            error_msg = f"❌ Error: The video is too large ({file_size_mb:.2f}MB). Telegram's limit for bot uploads is 50MB."
            await context.bot.edit_message_text(
                error_msg, chat_id=chat_id, message_id=processing_message_id
            )
            return

        await context.bot.edit_message_text(
            "⬆️ Uploading to Telegram...",
            chat_id=chat_id,
            message_id=processing_message_id,
        )

        with open(video_filename, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                disable_notification=True,
            )

        await context.bot.delete_message(
            chat_id=chat_id, message_id=processing_message_id
        )

    except DownloadError as de:
        logger.error(f"Download failed for URL {url}: {de}")
        # Attempt gallery-dl fallback first
        success = await send_via_gallery_dl(update, context, url, processing_message_id, purpose="fallback")
        if success:
            return
        if is_image_url(url):
            await download_and_send_images(update, context, url, processing_message_id)
            return
        error_message = "❌ Download Failed. The link might be private, broken, or from an unsupported site."
        await context.bot.edit_message_text(
            error_message, chat_id=chat_id, message_id=processing_message_id
        )

    except FileNotFoundError as fnfe:
        logger.error(f"File not found error after download for URL {url}: {fnfe}")
        # gallery-dl fallback
        success = await send_via_gallery_dl(update, context, url, processing_message_id, purpose="fallback")
        if success:
            return
        await context.bot.edit_message_text(
            "❌ An error occurred while saving the file. Please try again.",
            chat_id=chat_id,
            message_id=processing_message_id,
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred for URL {url}: {e}", exc_info=True)
        # gallery-dl fallback before final error
        try:
            success = await send_via_gallery_dl(update, context, url, processing_message_id, purpose="fallback")
            if success:
                return
        except Exception:
            pass
        if "Message to delete not found" not in str(
            e
        ) and "Message to edit not found" not in str(e):
            await context.bot.edit_message_text(
                "❌ An unexpected error occurred. Please try again later.",
                chat_id=chat_id,
                message_id=processing_message_id,
            )

    finally:
        if video_filename and os.path.exists(video_filename):
            try:
                os.remove(video_filename)
                logger.info(f"Cleaned up downloaded file: {video_filename}")
            except OSError as e:
                logger.error(f"Error removing file {video_filename}: {e}")


def is_image_url(url: str) -> bool:
    """
    Checks if a URL points directly to an image file or is likely to be an image gallery.
    Uses file extension or gallery-dl extractor check.
    """
    image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff")
    if any(url.lower().endswith(ext) for ext in image_exts):
        return True
    if gallery_dl:
        try:
            extractors = list(gallery_dl.config.extractors())
            logger.debug(f"Available extractors: {extractors}")
            for ext in extractors:
                if ext in url:
                    return True
        except Exception:
            pass
    return False


async def download_and_send_images(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    processing_message_id: int,
):
    """
    Downloads images from a URL using gallery-dl and sends them as photos.
    """
    import glob
    import shutil
    chat_id = update.effective_chat.id
    download_dir = "downloads/images"
    image_files = []
    try:
        await context.bot.edit_message_text(
            "🖼️ Downloading image(s)...", chat_id=chat_id, message_id=processing_message_id
        )
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
        if gallery_dl is not None:
            config = gallery_dl.config.Config()
            config.set("base-directory", download_dir)
            result = gallery_dl.job.Job(url, config)
            result.run()
        else:
            import subprocess
            subprocess.run(
                ["gallery-dl", "-d", download_dir, url],
                check=True,
                capture_output=True,
            )
        image_files = sorted(
            glob.glob(os.path.join(download_dir, "**", "*.*"), recursive=True)
        )
        image_files = [f for f in image_files if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"))]
        if not image_files:
            await context.bot.edit_message_text(
                "❌ Could not extract any images from the link.",
                chat_id=chat_id,
                message_id=processing_message_id,
            )
            return
        if len(image_files) > 1:
            from telegram import InputMediaPhoto
            media = [InputMediaPhoto(open(f, "rb")) for f in image_files[:10]]
            await update.message.reply_media_group(media=media, disable_notification=True)
            for m in media:
                m.media.close()
        else:
            with open(image_files[0], "rb") as img:
                await update.message.reply_photo(photo=img, disable_notification=True)
        await context.bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
    except Exception as e:
        logger.error(f"Image download failed for URL {url}: {e}", exc_info=True)
        await context.bot.edit_message_text(
            "❌ Failed to download image(s) from the link.",
            chat_id=chat_id,
            message_id=processing_message_id,
        )
    finally:
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)


async def handle_bad_bot_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles replies with 'bad bot' to a video message.
    Redownloads the video with Telegram-optimized settings and edits the original message.
    """
    if not update.message or not update.message.reply_to_message:
        return

    if "bad bot" not in update.message.text.lower():
        return

    replied_msg = update.message.reply_to_message

    url = None
    if replied_msg.caption:
        url = extract_url(replied_msg.caption)
    if not url and replied_msg.text:
        url = extract_url(replied_msg.text)
    if not url:
        await update.message.reply_text("❌ Could not find a URL in the original message.", disable_notification=True)
        return

    chat_id = update.effective_chat.id
    message_id = replied_msg.message_id

    tg_ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s_telegram.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
        "postprocessor_args": [
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "26",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-vf", "scale='min(720,iw)':-2"
        ],
    }

    video_filename = None
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
        status_msg = await update.message.reply_text("🔄 Reprocessing video for Telegram compatibility...", disable_notification=True)

        with YoutubeDL(tg_ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_filename = ydl.prepare_filename(info_dict)

        if not video_filename or not os.path.exists(video_filename):
            await status_msg.edit_text("❌ Failed to download or process the video.")
            return

        file_size_mb = os.path.getsize(video_filename) / (1024 * 1024)
        if file_size_mb > 50:
            await status_msg.edit_text(f"❌ The processed video is too large for Telegram ({file_size_mb:.2f}MB).")
            return

        with open(video_filename, "rb") as video_file:
            await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=InputMediaVideo(
                    media=video_file,
                    caption=replied_msg.caption or "",
                    supports_streaming=True,
                ),
            )
        await status_msg.edit_text("✅ Video replaced with Telegram-optimized version.")

    except Exception as e:
        logger.error(f"Error in bad bot reply handler: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to reprocess and replace the video.", disable_notification=True)

    finally:
        if video_filename and os.path.exists(video_filename):
            try:
                os.remove(video_filename)
            except Exception:
                pass


async def handle_gork_is_this_real(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles replies with '@gork is this real' by sending the original message's content
    to Gemini API and replying with a short answer.
    """
    if not update.message or not update.message.reply_to_message:
        return

    if "@gork is this real" not in update.message.text.lower():
        return

    original_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if not original_text:
        await update.message.reply_text("❌ Could not find any text in the original message.", disable_notification=True)
        return

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        await update.message.reply_text("❌ Gemini API key not set in environment variable.", disable_notification=True)
        return

    prompt = f"You are truth telling bot named Gork. People ask you @gork is this real. Don't say @gork is this real in your reply and don't start the reply with 'Oh,' or 'Well,' Try to be creative with your starting word. You find out if a statement is fact or fiction. Is the following statement real/truth/fact? Reply with a short answer in a sarcastic tone but be nice about it. If it's not a factoid or something you can discern is truth make it into a joke.\n\nStatement: {original_text}"

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
            headers = {"Content-Type": "application/json", "X-goog-api-key": gemini_api_key}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json()
                logger.info(f"Gemini API response: {data}")
                try:
                    reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    reply_text = "❌ Gemini API did not return a valid response."
                await update.message.reply_text(reply_text, disable_notification=True)
    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        await update.message.reply_text("❌ Failed to get a response from Gemini API.", disable_notification=True)


def main() -> None:
    """Set up the application and run the bot."""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    if TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print(
            "!!! PLEASE SET YOUR TELEGRAM BOT TOKEN IN THE SCRIPT OR ENVIRONMENT VARIABLE !!!"
        )
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(
            filters.REPLY & filters.TEXT & filters.Regex(r"(?i)\bbad bot\b"),
            handle_bad_bot_reply,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.REPLY & filters.TEXT & filters.Regex(r"(?i)@gork is this real"),
            handle_gork_is_this_real,
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()