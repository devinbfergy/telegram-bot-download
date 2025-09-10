from __future__ import annotations
import re
from app.core.types import MediaKind

_video_hosts = re.compile(r"(youtube|vimeo|tiktok|instagram|twitter|x)\.")
_image_ext = {"jpg","jpeg","png","gif","webp"}

def is_video_url(url: str) -> bool:
    return bool(_video_hosts.search(url)) or any(p in url for p in ("/video", "?video"))

def is_image_url(url: str) -> bool:
    return url.split("?")[0].lower().rstrip('/').split('.')[-1] in _image_ext

def classify_url(url: str) -> MediaKind:
    if is_video_url(url):
        return MediaKind.VIDEO
    if is_image_url(url):
        return MediaKind.IMAGE
    return MediaKind.OTHER
