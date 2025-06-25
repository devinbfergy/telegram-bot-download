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
from yt_dlp.utils import DownloadError, ExtractorError

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


def is_youtube_url(url: str) -> bool:
    """
    Checks if the URL is a standard YouTube video link or a YouTube Shorts link.
    This regex covers:
    - youtube.com/watch?v=VIDEO_ID
    - youtube.com/shorts/VIDEO_ID
    - youtu.be/VIDEO_ID
    - m.youtube.com/watch?v=VIDEO_ID (mobile links)
    """
    youtube_pattern = (
        r"(?:https?://)?(?:www\.)?(?:m\.)?"  # Optional http/https, www, m.
        r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)"  # Domain and path segment
        r"([a-zA-Z0-9_-]{11})"  # 11-character video ID (Fixed: a-Z to a-zA-Z)
    )
    return re.match(youtube_pattern, url) is not None


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
    It first checks if the URL is supported by yt-dlp. A progress message is only sent
    if the URL is validated as a downloadable video. If the URL is not supported,
    no message is sent back to the user.
    """
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    url = extract_url(message_text)

    if url:
        try:
            # First, check if the URL is recognized by yt-dlp without verbose output
            # We use `download=False` and `process=False` to only check if the URL
            # is recognized by an extractor, without fetching actual video info or downloading.
            with YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                ydl.extract_info(url, download=False, process=False)
            
            # If no exception, the URL is likely supported. Now send the initial processing message.
            processing_message = await update.message.reply_text(
                "✅ URL is supported. Preparing to download..."
            )
            await download_and_send_video(
                update, context, url, processing_message.message_id
            )

        except (DownloadError, ExtractorError) as e:
            # If validation fails, do not send any message back to the user.
            # Just log the warning.
            logger.warning(f"URL {url} not supported by yt-dlp or invalid: {e}")
        except Exception as e:
            # For other unexpected errors during validation, also do not send a message.
            # Just log the error.
            logger.error(f"An unexpected error occurred during URL validation for {url}: {e}", exc_info=True)


async def download_and_send_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    processing_message_id: int,
):
    """
    Downloads a video from a URL using yt-dlp, providing status updates to the user,
    and sends the final video file back. It uses optimized settings for YouTube videos
    (both standard and shorts) and general settings for other sites.
    """
    chat_id = update.effective_chat.id
    video_filename = None

    # --- Common yt-dlp Options for all downloads (default) ---
    # These options prioritize MP4 format, 720p resolution where possible,
    # and handle merging video/audio if they are separate streams.
    # It also enables quiet mode and basic post-processing for conversion and metadata.
    default_ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "noplaylist": True,  # Do not download entire playlists
        "quiet": True,  # Suppress console output
        "no_warnings": True,  # Suppress warnings
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",  # Ensure final output is MP4
            },
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,  # Add video metadata
            },
        ],
        "postprocessor_args": [
            "-c:v", "libx64",  # Video codec
            "-preset", "medium",  # Encoding speed vs. compression efficiency
            "-crf", "28",  # Constant Rate Factor for quality (higher is lower quality)
            "-c:a", "aac",  # Audio codec
            "-b:a", "128k",  # Audio bitrate
            "-pix_fmt", "yuv420p",  # Pixel format for compatibility
            "-movflags", "+faststart",  # Optimize for streaming (metadata at start)
        ],
    }

    # --- Specific YDL options for YouTube (standard videos and shorts) ---
    # These override or supplement the default options if the URL is from YouTube.
    # We include `skip_dash_manifest` for YouTube for better performance.
    youtube_ydl_opts = {**default_ydl_opts, **{
        "extractor_args": {"youtube": {"skip_dash_manifest": True}},
        # Potentially adjust format for YouTube if specific quality is desired,
        # but `bestvideo[ext=mp4][height<=720]+bestaudio` is usually good.
    }}

    # --- Select the appropriate options based on the URL ---
    if is_youtube_url(url):
        logger.info(f"YouTube link detected. Using specific settings for: {url}")
        ydl_opts = youtube_ydl_opts
    else:
        logger.info(f"Non-YouTube link detected. Using default settings for: {url}")
        ydl_opts = default_ydl_opts

    try:
        await context.bot.edit_message_text(
            "📥 Downloading...", chat_id=chat_id, message_id=processing_message_id
        )

        with YoutubeDL(ydl_opts) as ydl:
            # Extract info and download the video
            info_dict = ydl.extract_info(url, download=True)
            # After download and processing, get the final filename.
            # yt-dlp might change the extension during post-processing (e.g., from .webm to .mp4).
            # The 'filepath' key in the info_dict after download contains the final path.
            video_filename = info_dict.get('filepath') or ydl.prepare_filename(info_dict)


        if not video_filename or not os.path.exists(video_filename):
            raise FileNotFoundError(
                f"Downloaded file not found on disk: {video_filename}"
            )

        file_size_mb = os.path.getsize(video_filename) / (1024 * 1024)
        if file_size_mb > 50:
            error_msg = (
                f"❌ Error: The video is too large ({file_size_mb:.2f}MB). "
                "Telegram's limit for bot uploads is 50MB."
            )
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
                supports_streaming=True,  # Allows Telegram to stream the video
                read_timeout=120,  # Increase timeout for potentially large uploads
                write_timeout=120,
            )

        # Delete the initial processing message once the video is sent
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
        # Avoid trying to edit/delete messages that might already be gone
        if "Message to delete not found" not in str(e) and \
           "Message to edit not found" not in str(e):
            await context.bot.edit_message_text(
                "❌ An unexpected error occurred. Please try again later.",
                chat_id=chat_id,
                message_id=processing_message_id,
            )

    finally:
        # Clean up the downloaded file regardless of success or failure
        if video_filename and os.path.exists(video_filename):
            try:
                os.remove(video_filename)
                logger.info(f"Cleaned up downloaded file: {video_filename}")
            except OSError as e:
                logger.error(f"Error removing file {video_filename}: {e}")


def main() -> None:
    """Set up the application and run the bot."""
    # Create the 'downloads' directory if it doesn't exist
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # Check if the API token is set
    if TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print(
            "!!! PLEASE SET YOUR TELEGRAM BOT TOKEN IN THE SCRIPT OR ENVIRONMENT VARIABLE !!!"
        )
        return

    # Initialize the Telegram Application builder
    application = Application.builder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot is running...")
    # Start polling for updates from Telegram
    application.run_polling()


if __name__ == "__main__":
    main()
