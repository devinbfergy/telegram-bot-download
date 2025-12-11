from __future__ import annotations
import re
from urllib.parse import urlparse
from app.core.exceptions import UnsupportedURLError, SizeLimitExceeded
from app.config.settings import TELEGRAM_FILE_LIMIT_MB

ALLOWED_SCHEMES = {"http", "https"}

def extract_url(text: str) -> str | None:
    """Extracts the first URL from a given text using a regex pattern."""
    url_pattern = r"(https?://[^\s/$.?#].[^\s]*)"
    match = re.search(url_pattern, text)
    return match.group(0) if match else None

def validate_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ALLOWED_SCHEMES or not p.netloc:
        raise UnsupportedURLError(f"Invalid URL: {url}")
    return url

def enforce_size_limit(size_bytes: int):
    if size_bytes > TELEGRAM_FILE_LIMIT_MB * 1024 * 1024:
        raise SizeLimitExceeded(f"File exceeds {TELEGRAM_FILE_LIMIT_MB}MB limit")
