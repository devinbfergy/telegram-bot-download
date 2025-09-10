from __future__ import annotations
from typing import Optional
from app.core.logging import get_logger

log = get_logger(__name__)

class StatusMessenger:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self._message = None  # telegram.Message | None

    async def send_or_edit(self, context, text: str):  # noqa: ANN001
        try:
            if self._message is None:
                self._message = await context.bot.send_message(chat_id=self.chat_id, text=text)  # type: ignore[attr-defined]
            else:
                await context.bot.edit_message_text(chat_id=self.chat_id, message_id=self._message.message_id, text=text)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            log.debug("status.update_fail")

    async def finalize(self, delete: bool = False):
        if delete and self._message is not None:
            try:
                await self._message.delete()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
