import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import is_image_url

def test_is_image_url_facebook():
    url = "https://www.facebook.com/share/1JSWz8bWur/?mibextid=wwXIfr"
    # We can't guarantee Facebook will always be detected as an image,
    # but we can check that the function runs and returns a boolean.
    result = is_image_url(url)
    assert result == True, "Function should return true for this url"