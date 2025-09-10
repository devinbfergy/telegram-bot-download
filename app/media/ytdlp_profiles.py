from __future__ import annotations
from typing import Any, Dict

_BASE_COMMON = {
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "noprogress": True,
    "retries": 3,
    "socket_timeout": 30,
}


def base_profile() -> Dict[str, Any]:
    return dict(_BASE_COMMON)

def video_best_profile() -> Dict[str, Any]:
    p = base_profile()
    p.update({
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
    })
    return p

def audio_only_profile() -> Dict[str, Any]:
    p = base_profile()
    p.update({
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    })
    return p

def lightweight_profile() -> Dict[str, Any]:
    p = base_profile()
    p.update({"format": "worst[ext=mp4]/worst"})
    return p

PROFILES = {
    "video_best": video_best_profile,
    "audio_only": audio_only_profile,
    "lightweight": lightweight_profile,
}
