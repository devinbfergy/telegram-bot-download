from __future__ import annotations
from typing import TYPE_CHECKING

from app.core.logging import get_logger

if TYPE_CHECKING:
    from telegram import Message

    from app.config.settings import AppSettings

log = get_logger(__name__)


class StatusMessenger:
    """Manages status messages for long-running operations."""

    def __init__(
        self,
        bot,  # noqa: ANN001
        chat_id: int,
        settings: AppSettings,
        message_thread_id: int | None = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.settings = settings
        self.message_thread_id = message_thread_id
        self._message: Message | None = None

    async def send_message(self, text: str) -> None:
        """Send a new status message."""
        try:
            self._message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                message_thread_id=self.message_thread_id,
                disable_notification=True,
            )
        except Exception:  # noqa: BLE001
            log.debug("Failed to send status message")

    async def edit_message(self, text: str) -> None:
        """Edit existing status message or send if none exists."""
        try:
            if self._message is None:
                await self.send_message(text)
            else:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self._message.message_id,
                    text=text,
                    message_thread_id=self.message_thread_id,
                )
        except Exception:  # noqa: BLE001
            log.debug("Failed to edit status message")

    async def delete_status_message(self) -> None:
        """Delete the status message if it exists."""
        if self._message is not None:
            try:
                await self._message.delete()
                self._message = None
            except Exception:  # noqa: BLE001
                log.debug("Failed to delete status message")

    def has_active_message(self) -> bool:
        """Check if there's an active status message."""
        return self._message is not None

    async def send_or_edit(self, context, text: str):  # noqa: ANN001
        """Legacy method for backwards compatibility."""
        await self.edit_message(text)

    async def finalize(self, delete: bool = False) -> None:
        """Legacy method for backwards compatibility."""
        if delete:
            await self.delete_status_message()
