from __future__ import annotations
from pathlib import Path
from app.core.types import DownloadResult, MediaKind
import subprocess, json
from app.core.exceptions import ExtractionFailed
from app.core.logging import get_logger
from typing import Optional

log = get_logger(__name__)

GALLERY_DL_BIN = "gallery-dl"

def try_gallery_dl(url: str, workdir: Path) -> DownloadResult | None:
    cmd = [GALLERY_DL_BIN, "--write-metadata", "-D", str(workdir), url]
    try:
        subprocess.check_call(cmd, cwd=workdir)
    except FileNotFoundError:
        log.debug("gallery-dl not installed, skipping")
        return None
    except subprocess.CalledProcessError as e:
        log.debug("gallery-dl failed code=%s", e.returncode)
        return None
    files = [p for p in workdir.iterdir() if p.is_file() and not p.name.endswith('.json')]
    if not files:
        return None
    title = _extract_title(workdir)
    kind = MediaKind.ALBUM if len(files) > 1 else MediaKind.IMAGE
    return DownloadResult(source_url=url, kind=kind, files=files, title=title)


def _extract_title(workdir: Path) -> Optional[str]:
    for meta in workdir.glob('*metadata*.json'):
        try:
            data = json.loads(meta.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                for key in ("title", "name", "id"):
                    if key in data and data[key]:
                        return str(data[key])[:200]
        except Exception:
            continue
    return None
