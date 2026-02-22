from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from enum import Enum, auto


class MediaKind(Enum):
    VIDEO = auto()
    IMAGE = auto()
    ALBUM = auto()
    SLIDESHOW = auto()
    OTHER = auto()


@dataclass(slots=True)
class DownloadResult:
    source_url: str
    kind: MediaKind
    files: list[Path]
    title: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None

    def primary_file(self) -> Path | None:
        return self.files[0] if self.files else None
