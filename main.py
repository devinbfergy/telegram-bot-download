import logging
import os
import re
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

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
    # This regex looks for youtube.com/shorts/ or youtu.be/ with a video ID that's typical for shorts
    youtube_pattern = (
        r"(?:https?://)?(?:www\.)?(?:m\.)?"  # Optional http/https, www, m.
        r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)"  # Domain and path segment
        r"([a-zA-Z0-9_-]{11})"  # 11-character video ID (Fixed: a-Z to a-zA-Z)
    )
    return re.match(youtube_pattern, url) is not None

def is_video_url(url):
    """
    Checks if a URL is a video URL that yt-dlp can actually extract
    metadata from, implying it could potentially be downloaded.
    For private channels like Telegram, this will likely still fail
    without authentication, which is what we want for actual validity.
    """
    ydl_opts = {
        'extract_flat': True, # Only extract top-level info, don't recurse into playlists
        'quiet': True,       # Suppress standard output
        'simulate': True,    # Still simulate, but we'll inspect the info dictionary
        'skip_download': True, # Don't download
        'force_generic_extractor': False, # Allow specific extractors
        'no_warnings': True, # Suppress warnings
        'dump_single_json': True, # For inspecting the output
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            logger.debug(info)
            # --- Specific checks based on the extracted 'info' ---
            # 1. Check if 'extractor' is recognized and not generic
            if info.get('extractor') == 'generic':
                # If it's a generic extractor, yt-dlp couldn't find a specific one,
                # which often means it's not a direct video or supported content.
                return False

            # 2. Check for the presence of video formats
            #    This is the strongest indicator of a *downloadable* video.
            #    For a simple video, 'formats' will be a list.
            #    For a playlist/channel, 'entries' might contain videos with formats.
            if 'formats' in info and len(info['formats']) > 0:
                return True
            
            # If it's a playlist or channel URL, check entries for formats
            if 'entries' in info and isinstance(info['entries'], list):
                for entry in info['entries']:
                    if entry and 'formats' in entry and len(entry['formats']) > 0:
                        return True
            
            # Additional check: If 'url' is present and points to a video file
            if 'url' in info and isinstance(info['url'], str) and ('video' in info['url'] or any(ext in info['url'] for ext in ['.mp4', '.mkv', '.webm', '.mov', '.avi'])):
                return True

            # If none of the above, it's likely not a direct video or properly recognized video content
            return False

        except DownloadError as e:
            # yt-dlp raises DownloadError for unsupported URLs,
            # videos that don't exist, or issues like requiring login.
            # print(f"DownloadError for {url}: {e}")
            return False
        except Exception as e:
            # Catch any other unexpected exceptions
            # print(f"An unexpected error occurred for {url}: {e}")
            return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_html(
        "<b>Video Downloader Bot is active!</b>\n\n"
        "I will automatically watch for messages containing video links from sites "
        "like YouTube, Instagram, and Facebook, and reply with the downloaded video. "
        "Just send a link in a message!"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles incoming text messages, extracts a URL, and attempts to download the video.
    """
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    url = extract_url(message_text)

    if url:
        if is_video_url(url):
            # Send an initial confirmation message and store it to provide progress updates.
            processing_message = await update.message.reply_text(
                "🔗 Link detected. Preparing to download..."
            )
            await download_and_send_video(
                update, context, url, processing_message.message_id
            )
        elif "snapchat" in url or "facebook" in url:
            processing_message = await update.message.reply_text(
                "🔗 Link detected. Preparing to download..."
            )
            await download_and_send_video(
                update, context, url, processing_message.message_id
            )


async def download_and_send_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    processing_message_id: int,
):
    """
    Downloads a video from a URL using yt-dlp, providing status updates to the user,
    and sends the final video file back. It uses different settings for YouTube Shorts.
    """
    chat_id = update.effective_chat.id
    video_filename = None

    # --- Original yt-dlp Options (for non-YouTube Shorts) ---
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

    # --- Corrected yt-dlp Options (specifically for YouTube Shorts) ---
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

    # --- Select the appropriate options based on the URL ---
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
            # After download and processing, get the final filename.
            video_filename = ydl.prepare_filename(info_dict)

        if not video_filename or not os.path.exists(video_filename):
            raise FileNotFoundError(
                f"Downloaded file not found on disk: {video_filename}"
            )

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
            )

        await context.bot.delete_message(
            chat_id=chat_id, message_id=processing_message_id
        )

    except DownloadError as de:
        logger.error(f"Download failed for URL {url}: {de}")
        error_message = "❌ Download Failed. The link might be private, broken, or from an unsupported site."
        await context.bot.edit_message_text(
            error_message, chat_id=chat_id, message_id=processing_message_id
        )

    except FileNotFoundError as fnfe:
        logger.error(f"File not found error after download for URL {url}: {fnfe}")
        await context.bot.edit_message_text(
            "❌ An error occurred while saving the file. Please try again.",
            chat_id=chat_id,
            message_id=processing_message_id,
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred for URL {url}: {e}", exc_info=True)
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
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
