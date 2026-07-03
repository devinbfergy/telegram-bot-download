"""
SQLite-backed message store.

- All messages are persisted to a local SQLite file.
- Messages older than 24 hours are pruned on every write.
- `get_recent_messages` returns the last N minutes of history for a chat.
- All I/O is delegated to a thread pool via `asyncio.to_thread` so the event
  loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

MESSAGE_RETENTION_SECONDS = 24 * 60 * 60  # 24 hours
DEFAULT_CONTEXT_MINUTES = 10


class StoredMessage(NamedTuple):
    username: str | None
    first_name: str | None
    message_text: str
    timestamp: float


# ---------------------------------------------------------------------------
# Synchronous helpers (run inside a thread)
# ---------------------------------------------------------------------------


def init_db_sync(db_path: str) -> None:
    """Create tables and indexes if they do not already exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id      INTEGER NOT NULL,
                user_id      INTEGER,
                username     TEXT,
                first_name   TEXT,
                message_text TEXT    NOT NULL,
                timestamp    REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_timestamp
            ON messages (chat_id, timestamp)
        """)
        conn.commit()
        logger.info("database.initialized db_path=%s", db_path)
    finally:
        conn.close()


def _store_message_sync(
    db_path: str,
    chat_id: int,
    user_id: int | None,
    username: str | None,
    first_name: str | None,
    message_text: str,
) -> None:
    now = time.time()
    cutoff = now - MESSAGE_RETENTION_SECONDS
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO messages (chat_id, user_id, username, first_name, message_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, username, first_name, message_text, now),
        )
        # Prune messages older than 24 h on every write to keep the DB small.
        deleted = conn.execute(
            "DELETE FROM messages WHERE timestamp < ?", (cutoff,)
        ).rowcount
        conn.commit()
        if deleted:
            logger.debug("database.pruned rows=%d", deleted)
    finally:
        conn.close()


def _get_recent_messages_sync(
    db_path: str,
    chat_id: int,
    minutes: int = DEFAULT_CONTEXT_MINUTES,
) -> list[StoredMessage]:
    cutoff = time.time() - (minutes * 60)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT username, first_name, message_text, timestamp
            FROM messages
            WHERE chat_id = ? AND timestamp > ?
            ORDER BY timestamp ASC
            """,
            (chat_id, cutoff),
        ).fetchall()
        return [StoredMessage(*row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Async public API
# ---------------------------------------------------------------------------


async def init_db(db_path: str) -> None:
    """Async wrapper – initialise the database (create tables/indexes)."""
    await asyncio.to_thread(init_db_sync, db_path)


async def store_message(
    db_path: str,
    chat_id: int,
    user_id: int | None,
    username: str | None,
    first_name: str | None,
    message_text: str,
) -> None:
    """Persist a single message and prune records older than 24 h."""
    await asyncio.to_thread(
        _store_message_sync,
        db_path,
        chat_id,
        user_id,
        username,
        first_name,
        message_text,
    )


async def get_recent_messages(
    db_path: str,
    chat_id: int,
    minutes: int = DEFAULT_CONTEXT_MINUTES,
) -> list[StoredMessage]:
    """Return all messages in *chat_id* from the last *minutes* minutes."""
    return await asyncio.to_thread(_get_recent_messages_sync, db_path, chat_id, minutes)
