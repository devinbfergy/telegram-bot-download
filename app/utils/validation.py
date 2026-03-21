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


TELEGRAM_CAPTION_LIMIT = 1024
DESCRIPTION_WORD_LIMIT = 15


def summarize_description(text: str | None, word_limit: int = DESCRIPTION_WORD_LIMIT) -> str:
    """
    Summarizes long descriptions to the first sentence if word count exceeds limit.

    Args:
        text: The description text to summarize. Can be None.
        word_limit: Maximum word count before summarization (default 15).

    Returns:
        First sentence with ellipsis if over limit, or original text if under limit.
        Returns empty string if input is None/empty.
    """
    if not text:
        return ""

    text = text.strip()
    if not text:
        return ""

    words = text.split()
    
    sentence_endings = r'[.!?]'
    match = re.search(sentence_endings, text)
    
    if match:
        first_sentence = text[:match.end()].strip()
        first_sentence_words = first_sentence.split()
        
        if len(first_sentence_words) > word_limit:
            return " ".join(first_sentence_words[:word_limit]) + "..."
        
        if len(words) > word_limit:
            return first_sentence + "..."
        
        return text
    
    if len(words) > word_limit:
        return " ".join(words[:word_limit]) + "..."
    
    return text


def truncate_caption(text: str | None, max_length: int = TELEGRAM_CAPTION_LIMIT) -> str:
    """
    Truncates text to fit within Telegram's caption limit.

    Args:
        text: The caption text to truncate. Can be None.
        max_length: Maximum length (default 1024 for Telegram).

    Returns:
        Truncated string, or empty string if input is None/empty.
    """
    if not text:
        return ""

    text = text.strip()
    if len(text) <= max_length:
        return text

    truncated = text[: max_length - 3]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]

    return truncated + "..."
