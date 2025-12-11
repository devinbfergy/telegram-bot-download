import pytest
from app.media.detectors import is_image_url


def test_is_image_url_facebook():
    url = "https://www.facebook.com/share/1JSWz8bWur/?mibextid=wwXIfr"
    # This test is not reliable, as facebook URLs are not always images.
    # The new is_image_url function will return False, which is acceptable.
    assert is_image_url(url) is False
