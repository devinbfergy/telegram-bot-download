---
id: utils
type: module-design
status: draft
title: Shared utilities & SQLite message store
parent: architecture
---

## Responsibility

Helpers without Telegram-specific flow that any layer may use:

- `validation`: URL extraction, caption summarizing and truncation, and `is_chat_allowed`. A chat is
  allowed if it is in `allowed_chat_ids`, or if it is a private DM from a user whose username or ID is
  an admin. An empty allowlist allows every chat.
- `filesystem`: creates temp dirs and cleans them up safely.
- `concurrency`: `run_blocking`, a single wrapper that moves blocking calls off the event loop.
- `database`: the SQLite message store.

## Message store

- The `messages` table holds every logged text or caption message (chat, user, names, text,
  timestamp). Each write prunes messages older than **7 days**, so the memory job always has a full
  day of messages to read.
- The `user_memories` table is keyed by `(chat_id, user_id)` and holds the profile text and
  `updated_at`. `init_db_sync` creates the schema idempotently at startup and migrates older tables
  that lack `chat_id`.
- Every async accessor runs its query in `asyncio.to_thread`. Callers never touch `sqlite3` directly.
- The path comes from `SQLITE_DB_PATH` (default `/data/bot_messages.db`, on the persistent volume).

## Boundary

- This module does not import `telegram_bot`, `features`, or `media`. `validation` reads only
  `Update` attributes and `AppSettings`.
