from typing import Any, Dict

# Base configuration common to all yt-dlp profiles
_BASE_PROFILE = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "outtmpl": "downloads/%(id)s.%(ext)s",
    "merge_output_format": "mp4",
}


def get_default_profile() -> Dict[str, Any]:
    """
    Standard profile for general video downloads.
    - Re-encodes to H.264/AAC for broad compatibility.
    - Sets a reasonable CRF (quality level) to balance quality and size.
    - Moves metadata to the start of the file for faster streaming.
    """
    profile = _BASE_PROFILE.copy()
    profile.update(
        {
            "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
        }
    )
    return profile


def get_shorts_profile() -> Dict[str, Any]:
    """
    Optimized profile for YouTube Shorts and similar short-form videos.
    - Simplified post-processing for speed.
    """
    profile = _BASE_PROFILE.copy()
    profile.update(
        {
            "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
    )
    return profile


def get_fallback_profile() -> Dict[str, Any]:
    """
    A simple fallback profile for when the default fails, especially with frozen frames.
    - Aims for the best single MP4 file without complex merging.
    """
    profile = _BASE_PROFILE.copy()
    profile.update(
        {
            "format": "best[ext=mp4]/best",
            "outtmpl": "downloads/%(id)s_fallback.%(ext)s",
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
    )
    return profile


def get_telegram_optimization_profile() -> Dict[str, Any]:
    """
    Profile for the 'bad bot' reprocessing feature.
    - Rescales video to a maximum width of 720p.
    - Adjusts CRF for a slightly better quality/size trade-off for re-uploads.
    """
    profile = _BASE_PROFILE.copy()
    profile.update(
        {
            "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": "downloads/%(id)s_telegram.%(ext)s",
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
                "26",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-vf",
                "scale='min(720,iw)':-2",
            ],
        }
    )
    return profile


# Dictionary mapping profile names to their generator functions
PROFILES = {
    "default": get_default_profile,
    "shorts": get_shorts_profile,
    "fallback": get_fallback_profile,
    "telegram": get_telegram_optimization_profile,
}
