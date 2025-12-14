import logging
import re

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)

# --- URL Pattern Matching ---

YOUTUBE_SHORTS_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:m\.)?"
    r"(?:youtube\.com/shorts/)"
    r"([a-zA-Z0-9_-]{11})"
)
INSTAGRAM_REEL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:m\.)?"
    r"(?:instagram\.com/(?:reel|reels|p)/)"
    r"([a-zA-Z0-9_-]+)"
)
TIKTOK_PHOTO_PATTERN = re.compile(r"tiktok\.com/@[^/]+/photo/\d+")
IMAGE_EXTENSION_PATTERN = re.compile(
    r"\.(jpg|jpeg|png|gif|webp|bmp|tiff)$", re.IGNORECASE
)


def is_youtube_shorts_url(url: str) -> bool:
    """Checks if the URL is a YouTube Shorts link."""
    return bool(YOUTUBE_SHORTS_PATTERN.match(url))


def is_instagram_reel_url(url: str) -> bool:
    """Checks if the URL is an Instagram reel or post link."""
    return bool(INSTAGRAM_REEL_PATTERN.search(url))


def is_tiktok_photo_url(url: str) -> bool:
    """Checks if the URL is a TikTok photo slideshow link."""
    return bool(TIKTOK_PHOTO_PATTERN.search(url))


def is_image_url(url: str) -> bool:
    """
    Checks if a URL points directly to an image file based on its extension.
    """
    return bool(IMAGE_EXTENSION_PATTERN.search(url.split("?")[0]))


def is_video_url(url: str) -> bool:
    """
    Checks if a URL is a video by attempting a metadata-only extraction with yt-dlp.
    This is a more reliable method than simple regex matching.
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
            if not info:
                return False
            # If the generic extractor is used, it's likely not a video
            if info.get("extractor") == "generic":
                return False
            # Check for available formats
            if "formats" in info and len(info["formats"]) > 0:
                return True
            # Check for entries in a playlist
            if "entries" in info and isinstance(info["entries"], list):
                return any(
                    entry and "formats" in entry and len(entry["formats"]) > 0
                    for entry in info["entries"]
                )
            # A direct video URL might be present
            if "url" in info and isinstance(info["url"], str):
                video_exts = [".mp4", ".mkv", ".webm", ".mov", ".avi"]
                return any(ext in info["url"] for ext in video_exts)
            return False
        except DownloadError:
            return False
        except Exception:
            # Broad exception to catch any other yt-dlp issues
            return False


def is_slideshow(info_dict: dict) -> bool:
    """
    Detects if the yt-dlp info dict represents a TikTok/Instagram slideshow (photo mode).
    """
    if not isinstance(info_dict, dict):
        return False

    # TikTok and Instagram slideshows are often represented as playlists of images
    if info_dict.get("_type") == "playlist" and info_dict.get("extractor_key") in (
        "TikTok",
        "Instagram",
    ):
        entries = info_dict.get("entries") or []
        if not entries:
            return False

        # Check if all entries are image-like
        image_like_count = sum(
            1
            for e in entries
            if e and (e.get("ext") or "").lower() in ("jpg", "jpeg", "png", "webp")
        )
        return image_like_count > 0 and image_like_count == len(
            [e for e in entries if e]
        )

    return False
