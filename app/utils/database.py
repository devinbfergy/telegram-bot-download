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

MESSAGE_RETENTION_SECONDS = 7 * 24 * 60 * 60  # 7 days (guarantees last day of messages are kept)
DEFAULT_CONTEXT_MINUTES = 10


class StoredMessage(NamedTuple):
    username: str | None
    first_name: str | None
    message_text: str
    timestamp: float
    user_id: int | None = None
    chat_id: int | None = None


class UserMemory(NamedTuple):
    user_id: int
    username: str | None
    first_name: str | None
    memory: str
    updated_at: float
    chat_id: int = 0


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

        # Check existing user_memories schema for migration
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(user_memories)").fetchall()
        ]
        if cols and "chat_id" not in cols:
            conn.execute("ALTER TABLE user_memories RENAME TO old_user_memories")
            conn.execute("""
                CREATE TABLE user_memories (
                    chat_id      INTEGER NOT NULL DEFAULT 0,
                    user_id      INTEGER NOT NULL,
                    username     TEXT,
                    first_name   TEXT,
                    memory       TEXT NOT NULL DEFAULT '',
                    updated_at   REAL NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            conn.execute("""
                INSERT INTO user_memories (chat_id, user_id, username, first_name, memory, updated_at)
                SELECT 0, user_id, username, first_name, memory, updated_at FROM old_user_memories
            """)
            conn.execute("DROP TABLE old_user_memories")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    chat_id      INTEGER NOT NULL DEFAULT 0,
                    user_id      INTEGER NOT NULL,
                    username     TEXT,
                    first_name   TEXT,
                    memory       TEXT NOT NULL DEFAULT '',
                    updated_at   REAL NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_memories_updated
            ON user_memories (updated_at)
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
        # Prune messages older than retention window on every write to keep DB small.
        deleted = conn.execute(
            "DELETE FROM messages WHERE timestamp < ?", (cutoff,)
        ).rowcount
        conn.commit()
        if deleted:
            logger.debug("database.pruned rows=%d", deleted)
    finally:
        conn.close()


def _record_user_interaction_sync(
    db_path: str,
    user_id: int,
    username: str | None,
    first_name: str | None,
    chat_id: int = 0,
) -> None:
    now = time.time()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_memories (chat_id, user_id, username, first_name, memory, updated_at)
            VALUES (?, ?, ?, ?, '', ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = COALESCE(excluded.username, user_memories.username),
                first_name = COALESCE(excluded.first_name, user_memories.first_name)
            """,
            (chat_id, user_id, username, first_name, now),
        )
        conn.commit()
    finally:
        conn.close()


def _set_user_memory_sync(
    db_path: str,
    user_id: int,
    username: str | None,
    first_name: str | None,
    memory: str,
    chat_id: int = 0,
) -> None:
    now = time.time()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_memories (chat_id, user_id, username, first_name, memory, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                username = COALESCE(excluded.username, user_memories.username),
                first_name = COALESCE(excluded.first_name, user_memories.first_name),
                memory = excluded.memory,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, username, first_name, memory, now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_user_memory_sync(
    db_path: str, user_id: int, chat_id: int | None = None
) -> UserMemory | None:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        logger.warning("database: could not connect to %s: %s", db_path, exc)
        return None
    try:
        if chat_id is not None:
            row = conn.execute(
                """
                SELECT user_id, username, first_name, memory, updated_at, chat_id
                FROM user_memories
                WHERE user_id = ? AND chat_id = ?
                """,
                (user_id, chat_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT user_id, username, first_name, memory, updated_at, chat_id
                FROM user_memories
                WHERE user_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return UserMemory(*row) if row else None
    except sqlite3.Error as exc:
        logger.warning("database: query failed in _get_user_memory_sync: %s", exc)
        return None
    finally:
        conn.close()


def _get_user_memories_sync(
    db_path: str, user_ids: list[int], chat_id: int | None = None
) -> dict[int, UserMemory]:
    if not user_ids:
        return {}
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        logger.warning("database: could not connect to %s: %s", db_path, exc)
        return {}
    try:
        placeholders = ",".join("?" for _ in user_ids)
        result: dict[int, UserMemory] = {}
        if chat_id is not None:
            # First fetch chat-specific memories
            params = list(user_ids) + [chat_id]
            rows = conn.execute(
                f"""
                SELECT user_id, username, first_name, memory, updated_at, chat_id
                FROM user_memories
                WHERE user_id IN ({placeholders}) AND chat_id = ?
                """,
                params,
            ).fetchall()
            for row in rows:
                result[row[0]] = UserMemory(*row)

            # For any users missing a chat-specific memory, fall back to their most recent memory
            missing_ids = [uid for uid in user_ids if uid not in result]
            if missing_ids:
                m_placeholders = ",".join("?" for _ in missing_ids)
                fallback_rows = conn.execute(
                    f"""
                    SELECT user_id, username, first_name, memory, updated_at, chat_id
                    FROM user_memories
                    WHERE user_id IN ({m_placeholders})
                    ORDER BY updated_at DESC
                    """,
                    missing_ids,
                ).fetchall()
                for row in fallback_rows:
                    if row[0] not in result:
                        result[row[0]] = UserMemory(*row)
        else:
            rows = conn.execute(
                f"""
                SELECT user_id, username, first_name, memory, updated_at, chat_id
                FROM user_memories
                WHERE user_id IN ({placeholders})
                ORDER BY updated_at DESC
                """,
                user_ids,
            ).fetchall()
            for row in rows:
                if row[0] not in result:
                    result[row[0]] = UserMemory(*row)
        return result
    except sqlite3.Error as exc:
        logger.warning("database: query failed in _get_user_memories_sync: %s", exc)
        return {}
    finally:
        conn.close()


def _get_all_user_memories_sync(db_path: str) -> list[UserMemory]:
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        logger.warning("database: could not connect to %s: %s", db_path, exc)
        return []
    try:
        rows = conn.execute(
            """
            SELECT user_id, username, first_name, memory, updated_at
            FROM user_memories
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [UserMemory(*row) for row in rows]
    except sqlite3.Error as exc:
        logger.warning("database: query failed in _get_all_user_memories_sync: %s", exc)
        return []
    finally:
        conn.close()


def _get_messages_for_last_day_sync(
    db_path: str, hours: float = 24.0
) -> list[StoredMessage]:
    cutoff = time.time() - (hours * 3600)
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        logger.warning("database: could not connect to %s: %s", db_path, exc)
        return []
    try:
        rows = conn.execute(
            """
            SELECT username, first_name, message_text, timestamp, user_id, chat_id
            FROM messages
            WHERE timestamp >= ? AND user_id IS NOT NULL
            ORDER BY timestamp ASC
            """,
            (cutoff,),
        ).fetchall()
        return [StoredMessage(*row) for row in rows]
    except sqlite3.Error as exc:
        logger.warning("database: query failed in _get_messages_for_last_day_sync: %s", exc)
        return []
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
            SELECT username, first_name, message_text, timestamp, user_id, chat_id
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
    """Persist a single message and prune records older than the retention window."""
    await asyncio.to_thread(
        _store_message_sync,
        db_path,
        chat_id,
        user_id,
        username,
        first_name,
        message_text,
    )


async def record_user_interaction(
    db_path: str,
    user_id: int,
    username: str | None,
    first_name: str | None,
    chat_id: int = 0,
) -> None:
    """Record that a user spoke to us, registering them in user_memories if not present."""
    await asyncio.to_thread(
        _record_user_interaction_sync,
        db_path,
        user_id,
        username,
        first_name,
        chat_id,
    )


async def set_user_memory(
    db_path: str,
    user_id: int,
    username: str | None,
    first_name: str | None,
    memory: str,
    chat_id: int = 0,
) -> None:
    """Save or update memory for a user in a specific chat."""
    await asyncio.to_thread(
        _set_user_memory_sync,
        db_path,
        user_id,
        username,
        first_name,
        memory,
        chat_id,
    )


async def get_user_memory(
    db_path: str,
    user_id: int,
    chat_id: int | None = None,
) -> UserMemory | None:
    """Retrieve memory record for a specific user ID (optionally scoped to a chat)."""
    return await asyncio.to_thread(_get_user_memory_sync, db_path, user_id, chat_id)


async def get_user_memories(
    db_path: str,
    user_ids: list[int],
    chat_id: int | None = None,
) -> dict[int, UserMemory]:
    """Retrieve memory records for a list of user IDs (optionally scoped to a chat)."""
    return await asyncio.to_thread(_get_user_memories_sync, db_path, user_ids, chat_id)


async def get_all_user_memories(
    db_path: str,
) -> list[UserMemory]:
    """Retrieve all stored user memories."""
    return await asyncio.to_thread(_get_all_user_memories_sync, db_path)


async def get_messages_for_last_day(
    db_path: str,
    hours: float = 24.0,
) -> list[StoredMessage]:
    """Retrieve all messages from the last N hours that have a non-null user_id."""
    return await asyncio.to_thread(_get_messages_for_last_day_sync, db_path, hours)


async def get_recent_messages(
    db_path: str,
    chat_id: int,
    minutes: int = DEFAULT_CONTEXT_MINUTES,
) -> list[StoredMessage]:
    """Return all messages in *chat_id* from the last *minutes* minutes."""
    return await asyncio.to_thread(_get_recent_messages_sync, db_path, chat_id, minutes)
