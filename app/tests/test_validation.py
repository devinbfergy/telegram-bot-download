"""Tests for validation utilities."""

import pytest

from app.core.exceptions import UnsupportedURLError, SizeLimitExceeded
from app.utils.validation import extract_url, validate_url, enforce_size_limit


def test_extract_url_basic():
    assert extract_url("https://example.com/video") == "https://example.com/video"


def test_extract_url_with_surrounding_text():
    text = "Check out this video: https://example.com/video it's awesome!"
    assert extract_url(text) == "https://example.com/video"


def test_extract_url_multiple_urls():
    text = "https://first.com and https://second.com"
    # Should extract first URL
    assert extract_url(text) == "https://first.com"


def test_extract_url_http():
    assert extract_url("http://example.com/page") == "http://example.com/page"


def test_extract_url_with_path():
    url = "https://example.com/path/to/video?v=123&t=456"
    assert extract_url(url) == url


def test_extract_url_no_url():
    assert extract_url("This text has no URL") is None


def test_extract_url_empty_string():
    assert extract_url("") is None


def test_validate_url_valid():
    url = "https://example.com/video"
    assert validate_url(url) == url


def test_validate_url_invalid():
    with pytest.raises(UnsupportedURLError):
        validate_url("not a url")


def test_validate_url_no_scheme():
    with pytest.raises(UnsupportedURLError):
        validate_url("example.com/video")


def test_validate_url_ftp_scheme():
    with pytest.raises(UnsupportedURLError):
        validate_url("ftp://example.com/file")


def test_enforce_size_limit_within_limit():
    # 45 MB is under the 50 MB limit
    size_bytes = 45 * 1024 * 1024
    enforce_size_limit(size_bytes)  # Should not raise


def test_enforce_size_limit_at_limit():
    # Exactly 50 MB
    size_bytes = 50 * 1024 * 1024
    enforce_size_limit(size_bytes)  # Should not raise


def test_enforce_size_limit_over_limit():
    # 51 MB exceeds the 50 MB limit
    size_bytes = 51 * 1024 * 1024
    with pytest.raises(SizeLimitExceeded):
        enforce_size_limit(size_bytes)


def test_enforce_size_limit_zero():
    enforce_size_limit(0)  # Should not raise


def test_enforce_size_limit_negative():
    # Negative sizes should not raise (invalid input but not over limit)
    enforce_size_limit(-1)  # Should not raise
