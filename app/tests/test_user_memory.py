from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from app.config.settings import AppSettings
from app.features.ai_truth_check import ai_truth_check
from app.features.mention_responder import respond_to_mention
from app.features.user_memory import (
    call_gemini_for_memory,
    get_memories_prompt_block,
    show_user_memory,
    update_all_user_memories,
    update_user_memory_from_messages,
    user_memory_cron_job,
)
from app.telegram_bot.handlers import handle_user_memory, log_message_to_db
from app.telegram_bot.router import register_jobs
from app.utils.database import (
    StoredMessage,
    get_all_user_memories,
    get_messages_for_last_day,
    get_user_memories,
    get_user_memory,
    init_db_sync,
    record_user_interaction,
    set_user_memory,
    store_message,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    """Create a temporary initialized SQLite database."""
    db_file = str(tmp_path / "test_messages.db")
    init_db_sync(db_file)
    return db_file


@pytest.fixture
def memory_settings(temp_db: str) -> AppSettings:
    """AppSettings pointing to the temporary test database."""
    return AppSettings(
        api_token="test_token",
        gemini_api_key="test_gemini_key",
        db_path=Path(temp_db),
        user_memory_enabled=True,
        user_memory_window_hours=24.0,
        allowed_chat_ids={1, 10, 42, 88, 99, -1001400184101, -5199749336},
    )


def _make_gemini_interactions_response(text: str) -> dict:
    return {
        "steps": [
            {
                "type": "model_output",
                "content": [{"text": text}],
            }
        ]
    }


def _make_session_mock(MockClientSession, mock_response):
    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_post_ctx)

    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    MockClientSession.return_value = mock_session_ctx
    return mock_session


# ---------------------------------------------------------------------------
# Database Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_user_interaction_new_and_update(temp_db: str):
    # Record new interaction
    await record_user_interaction(temp_db, user_id=101, username="alice", first_name="Alice")
    mem = await get_user_memory(temp_db, 101)
    assert mem is not None
    assert mem.user_id == 101
    assert mem.username == "alice"
    assert mem.first_name == "Alice"
    assert mem.memory == ""

    # Set actual memory text
    await set_user_memory(temp_db, 101, "alice", "Alice", "- Loves Python and coffee.")
    mem = await get_user_memory(temp_db, 101)
    assert mem.memory == "- Loves Python and coffee."

    # Interacting again should update name but preserve memory
    await record_user_interaction(temp_db, user_id=101, username="alice_new", first_name="Alice B")
    mem = await get_user_memory(temp_db, 101)
    assert mem.username == "alice_new"
    assert mem.first_name == "Alice B"
    assert mem.memory == "- Loves Python and coffee."


@pytest.mark.asyncio
async def test_get_user_memories_bulk_and_all(temp_db: str):
    await set_user_memory(temp_db, 1, "u1", "User 1", "Memory 1")
    await set_user_memory(temp_db, 2, "u2", "User 2", "Memory 2")
    await set_user_memory(temp_db, 3, "u3", "User 3", "Memory 3")

    bulk = await get_user_memories(temp_db, [1, 3, 999])
    assert set(bulk.keys()) == {1, 3}
    assert bulk[1].memory == "Memory 1"
    assert bulk[3].memory == "Memory 3"

    all_mems = await get_all_user_memories(temp_db)
    assert len(all_mems) == 3


@pytest.mark.asyncio
async def test_get_messages_for_last_day(temp_db: str):
    # Message within window with user_id
    await store_message(temp_db, chat_id=10, user_id=1, username="u1", first_name="F1", message_text="Hello today")
    # Message within window without user_id (anonymous)
    await store_message(temp_db, chat_id=10, user_id=None, username=None, first_name=None, message_text="Anon message")

    msgs = await get_messages_for_last_day(temp_db, hours=24.0)
    assert len(msgs) == 1
    assert msgs[0].user_id == 1
    assert msgs[0].message_text == "Hello today"


# ---------------------------------------------------------------------------
# Feature & Gemini Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.features.user_memory.aiohttp.ClientSession")
async def test_call_gemini_for_memory_interactions_shape(mock_client_session, memory_settings):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(
        return_value=_make_gemini_interactions_response("- Enjoys hiking and coding.")
    )
    _make_session_mock(mock_client_session, mock_resp)

    res = await call_gemini_for_memory("Summarize user", memory_settings)
    assert res == "- Enjoys hiking and coding."


@pytest.mark.asyncio
@patch("app.features.user_memory.aiohttp.ClientSession")
async def test_call_gemini_for_memory_candidates_shape(mock_client_session, memory_settings):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(
        return_value={
            "candidates": [
                {"content": {"parts": [{"text": "- Candidate summary."}]}}
            ]
        }
    )
    _make_session_mock(mock_client_session, mock_resp)

    res = await call_gemini_for_memory("Summarize user", memory_settings)
    assert res == "- Candidate summary."


@pytest.mark.asyncio
async def test_call_gemini_no_api_key(temp_db: str):
    no_key_settings = AppSettings(gemini_api_key="", db_path=Path(temp_db))
    res = await call_gemini_for_memory("Prompt", no_key_settings)
    assert res is None


@pytest.mark.asyncio
@patch("app.features.user_memory.call_gemini_for_memory", new_callable=AsyncMock)
async def test_update_user_memory_from_messages(mock_call_gemini, memory_settings):
    mock_call_gemini.return_value = "- Frequent poster, sarcastic humor."

    msgs = [
        StoredMessage(username="bob", first_name="Bob", message_text="why is it raining", timestamp=time.time(), user_id=42, chat_id=10)
    ]
    res = await update_user_memory_from_messages(
        user_id=42,
        username="bob",
        first_name="Bob",
        messages=msgs,
        settings=memory_settings,
    )
    assert res == "- Frequent poster, sarcastic humor."

    # Check that database was updated
    saved = await get_user_memory(str(memory_settings.db_path), 42)
    assert saved is not None
    assert saved.memory == "- Frequent poster, sarcastic humor."


@pytest.mark.asyncio
@patch("app.features.user_memory.call_gemini_for_memory", new_callable=AsyncMock)
async def test_update_all_user_memories(mock_call_gemini, memory_settings):
    mock_call_gemini.return_value = "- Active user profile."
    db_path = str(memory_settings.db_path)

    # Store messages for two users
    await store_message(db_path, chat_id=1, user_id=100, username="user1", first_name="U1", message_text="msg 1")
    await store_message(db_path, chat_id=1, user_id=200, username="user2", first_name="U2", message_text="msg 2")

    stats = await update_all_user_memories(memory_settings, hours=24.0)
    assert stats["total_users"] == 2
    assert stats["updated"] == 2

    m100 = await get_user_memory(db_path, 100)
    m200 = await get_user_memory(db_path, 200)
    assert m100.memory == "- Active user profile."
    assert m200.memory == "- Active user profile."


@pytest.mark.asyncio
async def test_get_memories_prompt_block(temp_db: str):
    await set_user_memory(temp_db, 10, "alice", "Alice", "Loves tea.")
    await set_user_memory(temp_db, 20, None, "Bob", "Builds robots.")
    await set_user_memory(temp_db, 30, "charlie", None, "")  # empty memory

    block = await get_memories_prompt_block(temp_db, [10, 20, 30, 999])
    assert "User Memories & Context" in block
    assert "Alice (@alice): Loves tea." in block
    assert "Bob: Builds robots." in block
    assert "charlie" not in block  # empty memory omitted


# ---------------------------------------------------------------------------
# Prompt Injection in Mention Responder & AI Truth Check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.features.mention_responder.aiohttp.ClientSession")
async def test_mention_responder_injects_user_memory(mock_session_cls, memory_settings):
    db_path = str(memory_settings.db_path)
    # Set a memory for user 555
    await set_user_memory(db_path, 555, "carol", "Carol", "Obsessed with quantum mechanics.")

    # Recent message from user 555
    await store_message(db_path, chat_id=99, user_id=555, username="carol", first_name="Carol", message_text="hey gork")

    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.text = "@gork tell us a fun fact"
    update.message.caption = None
    update.effective_chat = MagicMock()
    update.effective_chat.id = 99
    update.message.from_user = MagicMock()
    update.message.from_user.id = 555
    update.message.from_user.username = "carol"
    update.message.from_user.first_name = "Carol"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=_make_gemini_interactions_response("Here is a fun quantum fact!"))
    mock_session = _make_session_mock(mock_session_cls, mock_resp)

    await respond_to_mention(update, context, memory_settings)

    # Check that Gemini was called with Carol's memory in the prompt
    post_calls = mock_session.post.call_args_list
    assert len(post_calls) > 0
    payload = post_calls[0][1]["json"]
    prompt = payload["input"]
    assert "Obsessed with quantum mechanics." in prompt
    assert "Carol (@carol)" in prompt


@pytest.mark.asyncio
@patch("app.features.ai_truth_check.aiohttp.ClientSession")
async def test_ai_truth_check_injects_user_memory(mock_session_cls, memory_settings):
    db_path = str(memory_settings.db_path)
    await set_user_memory(db_path, 777, "dave", "Dave", "Professional skeptic.")

    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.text = "@gork is this real"
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "Birds are government drones."
    update.message.reply_to_message.caption = None
    update.message.reply_to_message.from_user = MagicMock()
    update.message.reply_to_message.from_user.id = 777
    update.message.from_user = MagicMock()
    update.message.from_user.id = 777

    update.effective_chat = MagicMock()
    update.effective_chat.id = 88
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=_make_gemini_interactions_response("No, birds are real animals."))
    mock_session = _make_session_mock(mock_session_cls, mock_resp)

    await ai_truth_check(update, context, memory_settings)

    post_calls = mock_session.post.call_args_list
    assert len(post_calls) > 0
    payload = post_calls[0][1]["json"]
    prompt = payload["input"]
    assert "Professional skeptic." in prompt


# ---------------------------------------------------------------------------
# Passive Interaction Logging & Job Registration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_message_to_db_records_user(memory_settings):
    db_path = str(memory_settings.db_path)

    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.text = "Just talking here"
    update.effective_chat = MagicMock()
    update.effective_chat.id = 42
    update.message.from_user = MagicMock()
    update.message.from_user.id = 888
    update.message.from_user.username = "active_user"
    update.message.from_user.first_name = "Active"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = MagicMock()
    context.application.settings = {"app_settings": memory_settings}

    await log_message_to_db(update, context)

    # User should now exist in user_memories
    user_record = await get_user_memory(db_path, 888)
    assert user_record is not None
    assert user_record.username == "active_user"
    assert user_record.first_name == "Active"


@pytest.mark.asyncio
async def test_log_message_to_db_records_caption(memory_settings):
    db_path = str(memory_settings.db_path)

    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.text = None
    update.message.caption = "Photo caption here"
    update.effective_chat = MagicMock()
    update.effective_chat.id = 42
    update.message.from_user = MagicMock()
    update.message.from_user.id = 999
    update.message.from_user.username = "photographer"
    update.message.from_user.first_name = "Photo"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = MagicMock()
    context.application.settings = {"app_settings": memory_settings}

    await log_message_to_db(update, context)

    user_record = await get_user_memory(db_path, 999)
    assert user_record is not None
    assert user_record.username == "photographer"

    msgs = await get_messages_for_last_day(db_path, hours=1.0)
    assert any(m.message_text == "Photo caption here" and m.user_id == 999 for m in msgs)


def test_register_jobs_with_job_queue():
    app = MagicMock()
    app.job_queue = MagicMock()
    settings = AppSettings(user_memory_enabled=True, user_memory_interval_hours=12.0)
    app.settings = {"app_settings": settings}

    register_jobs(app)

    app.job_queue.run_repeating.assert_called_once()
    kwargs = app.job_queue.run_repeating.call_args.kwargs
    assert kwargs["name"] == "user_memory_update"
    assert kwargs["interval"] == 12.0 * 3600


@pytest.mark.asyncio
@patch("app.features.user_memory.update_all_user_memories", new_callable=AsyncMock)
async def test_user_memory_cron_job_execution(mock_update_all, memory_settings):
    mock_update_all.return_value = {"updated": 1, "total_users": 1}

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = MagicMock()
    context.application.settings = {"app_settings": memory_settings}

    await user_memory_cron_job(context)
    mock_update_all.assert_called_once_with(memory_settings)


@pytest.mark.asyncio
async def test_show_user_memory_no_memory(memory_settings):
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = None
    update.message.from_user = MagicMock()
    update.message.from_user.id = 1234
    update.message.from_user.first_name = "Newbie"
    update.message.from_user.username = "newbie"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    await show_user_memory(update, context, memory_settings)

    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "don't have any memories" in args[0]
    assert kwargs["disable_notification"] is True


@pytest.mark.asyncio
@patch("app.features.user_memory.call_gemini_for_memory", new_callable=AsyncMock)
async def test_show_user_memory_with_gemini(mock_call_gemini, memory_settings):
    db_path = str(memory_settings.db_path)
    await set_user_memory(db_path, 4321, "alice", "Alice", "- Loves tea and puzzles.")

    mock_call_gemini.return_value = "Here is Alice. Sarcastic tea lover:\n- Solves puzzles daily."

    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.message.reply_to_message = None
    update.message.from_user = MagicMock()
    update.message.from_user.id = 4321
    update.message.from_user.first_name = "Alice"
    update.message.from_user.username = "alice"

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    await show_user_memory(update, context, memory_settings)

    update.message.reply_text.assert_called_once_with(
        "Here is Alice. Sarcastic tea lover:\n- Solves puzzles daily.",
        disable_notification=True,
    )


@pytest.mark.asyncio
@patch("app.features.user_memory.call_gemini_for_memory", new_callable=AsyncMock)
async def test_show_user_memory_replied_user(mock_call_gemini, memory_settings):
    db_path = str(memory_settings.db_path)
    await set_user_memory(db_path, 9999, "target", "TargetUser", "- Loves robots.")

    mock_call_gemini.return_value = "TargetUser is an engineer."

    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    # User replying to someone else
    update.message.from_user = MagicMock()
    update.message.from_user.id = 1111

    replied = MagicMock()
    replied.from_user = MagicMock()
    replied.from_user.id = 9999
    replied.from_user.first_name = "TargetUser"
    replied.from_user.username = "target"
    update.message.reply_to_message = replied

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    await show_user_memory(update, context, memory_settings)

    update.message.reply_text.assert_called_once_with(
        "TargetUser is an engineer.",
        disable_notification=True,
    )


@pytest.mark.asyncio
@patch("app.telegram_bot.handlers.show_user_memory", new_callable=AsyncMock)
async def test_handle_user_memory_handler(mock_show, memory_settings):
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.update_id = 123
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.application = MagicMock()
    context.application.settings = {"app_settings": memory_settings}

    await handle_user_memory(update, context)
    mock_show.assert_called_once_with(update, context, memory_settings)
