from __future__ import annotations
import re
from app.config.strings import MESSAGES
from app.media.pipeline import MediaPipeline
from app.telegram_bot.status_messenger import StatusMessenger
from app.core.logging import get_logger

log = get_logger(__name__)

pipeline = MediaPipeline()
_URL_RE = re.compile(r"https?://\S+")

async def start(update, context):  # noqa: ANN001
    chat_id = getattr(getattr(update, 'effective_chat', None), 'id', None)
    if chat_id is not None:
        try:
            await context.bot.send_message(chat_id=chat_id, text=MESSAGES["start"])  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.debug("start.send_fail")

async def handle_text(update, context):  # noqa: ANN001
    chat = getattr(update, 'effective_chat', None)
    chat_id = getattr(chat, 'id', None)
    text = getattr(getattr(update, 'message', None), 'text', '') or ''
    urls = _URL_RE.findall(text)
    if not urls:
        return
    for url in urls:
        status = StatusMessenger(chat_id)
        await status.send_or_edit(context, MESSAGES["downloading"])
        try:
            await pipeline.process(url.strip(), context, chat_id)
            await status.send_or_edit(context, MESSAGES["sending"])
        except Exception:  # noqa: BLE001
            log.exception("handler.error url=%s", url)
            await status.send_or_edit(context, MESSAGES["error_generic"])
        finally:
            await status.finalize(delete=False)
