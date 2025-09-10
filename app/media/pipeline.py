from __future__ import annotations
from pathlib import Path
from typing import Any
from app.utils.validation import validate_url
from app.utils.validation import enforce_size_limit
from app.utils.filesystem import temp_workspace
from app.media.gallery_dl import try_gallery_dl
from app.media.downloader import download_url
from app.media.send import send_video, send_image, send_album, send_document
from app.core.types import DownloadResult, MediaKind
from app.core.logging import get_logger
from shutil import copy2
from app.media.postprocess import ensure_mp4, normalize_audio
from app.media.slideshow import build_slideshow
from app.media.inspection import detect_frozen_frames
from app.config import settings
from app.utils.cache import LRUCache
from app.features.ai_truth_check import ai_truth_check

log = get_logger(__name__)

_cache = LRUCache(maxsize=64)
_persist_dir = settings.DOWNLOAD_BASE_DIR / "cache"
_persist_dir.mkdir(parents=True, exist_ok=True)

class MediaPipeline:
    async def process(self, url: str, context: Any, chat_id: int) -> DownloadResult:  # noqa: ANN401
        cached = _cache.get(url)
        if cached:
            log.info("pipeline.cache_hit url=%s", url)
            result = self._hydrate_cached(url, cached)
            await self._send(result, context, chat_id)
            return result
        url = validate_url(url)
        log.info("pipeline.start url=%s", url)
        with temp_workspace("pipeline_") as workdir:
            result = try_gallery_dl(url, workdir)
            if result is None:
                result = download_url(url, workdir)
            result = self._maybe_slideshow(result, workdir)
            result = self._postprocess(result)
            self._inspect(result)
            result = self._persist(result)
            _cache.set(url, self._serialize(result))
            await self._send(result, context, chat_id)
            log.info("pipeline.done kind=%s files=%d", result.kind, len(result.files))
            return result

    async def _send(self, result: DownloadResult, context: Any, chat_id: int):  # noqa: ANN401
        caption: str | None = None
        parts: list[str] = []
        if result.title:
            parts.append(result.title[:900])
        if parts and settings.AI_TRUTH_CHECK_ENABLED:
            try:
                note = await ai_truth_check(result.title or "")
                if note:
                    parts.append(note)
            except Exception:  # noqa: BLE001
                log.debug("pipeline.ai_caption_skip")
        if parts:
            caption = "\n".join(parts)
        if result.kind == MediaKind.VIDEO:
            await send_video(context, chat_id, result.primary_file(), caption=caption)  # type: ignore[arg-type]
        elif result.kind == MediaKind.IMAGE:
            await send_image(context, chat_id, result.primary_file(), caption=caption)  # type: ignore[arg-type]
        elif result.kind == MediaKind.ALBUM:
            await send_album(context, chat_id, result.files, caption=caption)
        else:
            if result.files:
                await send_document(context, chat_id, result.primary_file(), caption=caption)  # type: ignore[arg-type]
            else:
                log.debug("send.fallback_no_files kind=%s", result.kind)

    def _maybe_slideshow(self, result: DownloadResult, workdir: Path) -> DownloadResult:
        if result.kind in {MediaKind.ALBUM, MediaKind.IMAGE}:
            images = [f for f in result.files if f.suffix.lower() in {'.jpg','.jpeg','.png','.gif','.webp'}]
            if len(images) > 1:
                out = workdir / "slideshow.mp4"
                try:
                    build_slideshow(images, out)
                    return DownloadResult(result.source_url, MediaKind.SLIDESHOW, [out], title=result.title)
                except Exception:  # noqa: BLE001
                    log.exception("pipeline.slideshow_failed")
        return result

    def _postprocess(self, result: DownloadResult) -> DownloadResult:
        if result.kind in {MediaKind.VIDEO, MediaKind.SLIDESHOW} and result.files:
            v = ensure_mp4(result.files[0])
            v = normalize_audio(v)
            result.files = [v]
        return result

    def _inspect(self, result: DownloadResult) -> None:
        if result.kind in {MediaKind.VIDEO, MediaKind.SLIDESHOW} and result.files:
            try:
                if detect_frozen_frames(result.files[0]):
                    log.warning("pipeline.frozen_frames url=%s", result.source_url)
            except Exception:  # noqa: BLE001
                log.debug("pipeline.inspect_skip")

    def _persist(self, result: DownloadResult) -> DownloadResult:
        new_files: list[Path] = []
        for f in result.files:
            target = _persist_dir / f.name
            if not target.exists():
                try:
                    copy2(f, target)
                except Exception:  # noqa: BLE001
                    log.debug("pipeline.copy_fail file=%s", f)
                    continue
            try:
                enforce_size_limit(target.stat().st_size)
            except Exception as e:  # noqa: BLE001
                log.warning("pipeline.size_exceeded file=%s err=%s", target, e)
                continue
            new_files.append(target)
        result.files = new_files or result.files
        return result

    def _serialize(self, result: DownloadResult) -> dict:
        return {
            "kind": result.kind.name,
            "files": [str(p) for p in result.files],
            "title": result.title,
            "duration": result.duration,
            "width": result.width,
            "height": result.height,
        }

    def _hydrate_cached(self, url: str, data: dict) -> DownloadResult:
        kind = MediaKind[data["kind"]]
        files = [Path(p) for p in data["files"] if Path(p).exists()]
        return DownloadResult(url, kind, files, data.get("title"), data.get("duration"), data.get("width"), data.get("height"))
