from __future__ import annotations
from pathlib import Path
from typing import Sequence
from app.core.logging import get_logger

log = get_logger(__name__)

# Placeholder send helpers (real implementation will use python-telegram-bot)

async def send_video(context, chat_id: int, file_path: Path, caption: str | None = None):  # noqa: ANN001
    try:
        return await context.bot.send_video(chat_id=chat_id, video=file_path.open('rb'), caption=caption)  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001
        log.exception("send.video_failed path=%s", file_path)

async def send_image(context, chat_id: int, file_path: Path, caption: str | None = None):  # noqa: ANN001
    try:
        return await context.bot.send_photo(chat_id=chat_id, photo=file_path.open('rb'), caption=caption)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        log.exception("send.image_failed path=%s", file_path)

async def send_document(context, chat_id: int, file_path: Path, caption: str | None = None):  # noqa: ANN001
    try:
        return await context.bot.send_document(chat_id=chat_id, document=file_path.open('rb'), caption=caption)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        log.exception("send.document_failed path=%s", file_path)

async def send_album(context, chat_id: int, files: Sequence[Path], caption: str | None = None):  # noqa: ANN001
    try:
        media = []
        from telegram import InputMediaPhoto  # type: ignore
        for idx, f in enumerate(files):
            cap = caption if idx == 0 else None
            media.append(InputMediaPhoto(media=f.open('rb'), caption=cap))
        return await context.bot.send_media_group(chat_id=chat_id, media=media)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        log.exception("send.album_failed count=%d", len(files))
