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
        bot,
        chat_id: int,
        settings: AppSettings,
        message_thread_id: int | None = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.settings = settings
        self.message_thread_id = message_thread_id
        self._message: Message | None = None
        self._terminal_error = False

    async def send_message(self, text: str) -> bool:
        """Send a new status message and report whether it became visible."""
        try:
            message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                message_thread_id=self.message_thread_id,
                disable_notification=True,
            )
        except Exception:  # noqa: BLE001
            self._message = None
            self._terminal_error = False
            log.debug("Failed to send status message")
            return False

        self._message = message
        self._terminal_error = False
        return True

    async def edit_message(self, text: str) -> bool:
        """Edit an existing status, replacing it if the stored message is stale."""
        if self._message is None:
            return await self.send_message(text)

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self._message.message_id,
                text=text,
                message_thread_id=self.message_thread_id,
            )
        except Exception:  # noqa: BLE001
            log.debug("Failed to edit status message; sending a replacement")
            self._message = None
            self._terminal_error = False
            return await self.send_message(text)

        self._terminal_error = False
        return True

    async def show_terminal_error(self, text: str) -> None:
        """Display an error and retain it instead of treating it as transient progress."""
        visible = await self.edit_message(text)
        self._terminal_error = visible

    async def delete_status_message(self) -> None:
        """Delete the status message if it exists."""
        if self._message is not None:
            try:
                await self._message.delete()
                self._message = None
                self._terminal_error = False
            except Exception:  # noqa: BLE001
                log.debug("Failed to delete status message")

    def has_active_message(self) -> bool:
        """Check if there's an active status message."""
        return self._message is not None

    def has_terminal_error(self) -> bool:
        """Return whether the active status is a terminal failure."""
        return self._terminal_error

    async def send_or_edit(self, context, text: str):
        """Legacy method for backwards compatibility."""
        await self.edit_message(text)

    async def finalize(self, delete: bool = False) -> None:
        """Legacy method for backwards compatibility."""
        if delete:
            await self.delete_status_message()
