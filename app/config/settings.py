from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Basic env loading (could later use python-dotenv)

def _get(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val or ""

BASE_DIR = Path(os.getenv("APP_BASE_DIR", Path.cwd()))
DOWNLOAD_BASE_DIR = BASE_DIR / "downloads"
DOWNLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Telegram limits
TELEGRAM_FILE_LIMIT_MB = 50
TELEGRAM_FILE_LIMIT_BYTES = TELEGRAM_FILE_LIMIT_MB * 1024 * 1024
TELEGRAM_UPLOAD_TIMEOUT = 120  # seconds
TELEGRAM_READ_TIMEOUT = 120  # seconds
TELEGRAM_WRITE_TIMEOUT = 120  # seconds

# Media file extensions
MEDIA_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv"}
MEDIA_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
MEDIA_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"}

# External tool timeouts
TIMEOUTS = {
    "yt_dlp": 600,
    "gallery_dl": 600,
    "ffmpeg": 900,
}

FROZEN_FRAME = {
    "sample_interval": 15,
    "similarity_threshold": 0.995,
}

SLIDESHOW = {
    "frame_duration": 2.5,
    "transition": "fade",
}

LOG_LEVEL = _get("LOG_LEVEL", "INFO")
LOG_JSON = _get("LOG_JSON", "0") in {"1", "true", "True"}

API_TOKEN = _get("API_TOKEN", required=False)
GEMINI_API_KEY = _get("GEMINI_API_KEY", required=False)
AI_TRUTH_CHECK_ENABLED = _get("AI_TRUTH_CHECK_ENABLED", "0") in {"1", "true", "True"}

@dataclass(slots=True)
class AppSettings:
    api_token: str = API_TOKEN
    gemini_api_key: str = GEMINI_API_KEY
    download_dir: Path = DOWNLOAD_BASE_DIR
    log_level: str = LOG_LEVEL
    log_json: bool = LOG_JSON
    timeouts: dict[str, int] = None  # type: ignore
    ai_truth_check_enabled: bool = AI_TRUTH_CHECK_ENABLED
    
    # Telegram settings
    telegram_max_video_size: int = TELEGRAM_FILE_LIMIT_BYTES
    telegram_upload_timeout: int = TELEGRAM_UPLOAD_TIMEOUT
    telegram_read_timeout: int = TELEGRAM_READ_TIMEOUT
    telegram_write_timeout: int = TELEGRAM_WRITE_TIMEOUT
    
    # Media file extensions
    media_video_extensions: set[str] = None  # type: ignore
    media_image_extensions: set[str] = None  # type: ignore
    media_audio_extensions: set[str] = None  # type: ignore

    def __post_init__(self):
        if self.timeouts is None:
            self.timeouts = TIMEOUTS.copy()
        if self.media_video_extensions is None:
            self.media_video_extensions = MEDIA_VIDEO_EXTENSIONS.copy()
        if self.media_image_extensions is None:
            self.media_image_extensions = MEDIA_IMAGE_EXTENSIONS.copy()
        if self.media_audio_extensions is None:
            self.media_audio_extensions = MEDIA_AUDIO_EXTENSIONS.copy()


def load_config() -> AppSettings:
    return AppSettings()
