from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import AppSettings
from app.media.gallery_dl import (
    _inspect_gallery_dl_metadata,
    download_and_send_with_gallery_dl,
)
from app.telegram_bot.handlers import handle_download_issues
from app.telegram_bot.status_messenger import StatusMessenger
from app.utils.database import (
    DownloadIssue,
    format_download_issues,
    get_recent_download_issues,
    init_db,
    record_download_issue,
)


@pytest.fixture
def temp_db(tmp_path: Path):
    db_file = tmp_path / "test_download_issues.db"
    return str(db_file)


@pytest.fixture
def settings(temp_db):
    s = AppSettings()
    s.db_path = Path(temp_db)
    return s


@pytest.mark.asyncio
async def test_db_record_and_get_download_issues(temp_db):
    await init_db(temp_db)

    # Initially empty
    issues = await get_recent_download_issues(temp_db, chat_id=123)
    assert issues == []

    # Record a complete failure
    await record_download_issue(
        db_path=temp_db,
        chat_id=123,
        url="https://instagram.com/p/fail123/",
        issue_type="failed",
        error_message="Instagram login required / cookies expired",
        user_id=456,
        username="alice",
        first_name="Alice",
    )

    # Record an incomplete album
    await record_download_issue(
        db_path=temp_db,
        chat_id=123,
        url="https://instagram.com/p/album456/",
        issue_type="incomplete_album",
        error_message="Only downloaded 3 of 8 photos in album",
        total_items=8,
        downloaded_items=3,
        user_id=789,
        username="bob",
        first_name="Bob",
    )

    # Different chat ID
    await record_download_issue(
        db_path=temp_db,
        chat_id=999,
        url="https://tiktok.com/@user/video/123",
        issue_type="failed",
        error_message="Video not found",
    )

    # Fetch for chat 123
    chat_123_issues = await get_recent_download_issues(temp_db, chat_id=123)
    assert len(chat_123_issues) == 2
    assert chat_123_issues[0].url == "https://instagram.com/p/album456/"
    assert chat_123_issues[0].issue_type == "incomplete_album"
    assert chat_123_issues[0].total_items == 8
    assert chat_123_issues[0].downloaded_items == 3
    assert chat_123_issues[0].first_name == "Bob"

    assert chat_123_issues[1].url == "https://instagram.com/p/fail123/"
    assert chat_123_issues[1].issue_type == "failed"

    # Fetch all chats
    all_issues = await get_recent_download_issues(temp_db)
    assert len(all_issues) == 3

    # Test format_download_issues
    formatted = format_download_issues(chat_123_issues)
    assert "[Incomplete Album]" in formatted
    assert "https://instagram.com/p/album456/" in formatted
    assert "Bob" in formatted
    assert "3 of 8" in formatted
    assert "[Failed Download]" in formatted
    assert "https://instagram.com/p/fail123/" in formatted


def test_inspect_gallery_dl_metadata(tmp_path: Path):
    # Create mock info json files
    json_path1 = tmp_path / "1.jpg.json"
    json_path1.write_text(
        '{"count": 5, "num": 1, "description": "Trip to Paris #travel"}',
        encoding="utf-8",
    )

    json_path2 = tmp_path / "2.jpg.json"
    json_path2.write_text('{"count": 5, "num": 2}', encoding="utf-8")

    caption, expected_count, file_num_map = _inspect_gallery_dl_metadata(tmp_path)
    assert "Trip to Paris" in caption
    assert expected_count == 5
    assert file_num_map["1.jpg"] == 1
    assert file_num_map["2.jpg"] == 2


@pytest.mark.asyncio
@patch("app.media.gallery_dl.run_blocking")
async def test_gallery_dl_single_photo(mock_run, tmp_path: Path, settings):
    # Simulate gallery-dl downloading a single photo
    status_messenger = MagicMock(spec=StatusMessenger)
    status_messenger.edit_message = AsyncMock()
    status_messenger.delete_status_message = AsyncMock()

    message = AsyncMock()
    message.chat_id = 123
    message.from_user = MagicMock(id=456, username="carol", first_name="Carol")

    # When gallery-dl runs, create 1 image in tmp_path
    async def fake_run(func, *args, **kwargs):
        temp_dir = args[1]
        img = temp_dir / "photo1.jpg"
        img.write_bytes(b"fake image data")

    mock_run.side_effect = fake_run

    result = await download_and_send_with_gallery_dl(
        url="https://instagram.com/p/single_photo/",
        message=message,
        status_messenger=status_messenger,
        settings=settings,
    )

    assert result is True
    # For single photo, reply_photo must be called, not reply_media_group
    message.reply_photo.assert_called_once()
    message.reply_media_group.assert_not_called()
    status_messenger.delete_status_message.assert_called_once()


@pytest.mark.asyncio
@patch("app.media.gallery_dl.run_blocking")
async def test_gallery_dl_album_chunks_over_10(mock_run, tmp_path: Path, settings):
    # Simulate an album of 12 photos
    status_messenger = MagicMock(spec=StatusMessenger)
    status_messenger.edit_message = AsyncMock()
    status_messenger.delete_status_message = AsyncMock()

    message = AsyncMock()
    message.chat_id = 123
    message.from_user = MagicMock(id=456, username="carol", first_name="Carol")

    async def fake_run(func, *args, **kwargs):
        temp_dir = args[1]
        for i in range(1, 13):
            img = temp_dir / f"{i:02d}.jpg"
            img.write_bytes(b"photo bytes")
            info = temp_dir / f"{i:02d}.jpg.json"
            info.write_text(f'{{"count": 12, "num": {i}}}', encoding="utf-8")

    mock_run.side_effect = fake_run

    result = await download_and_send_with_gallery_dl(
        url="https://instagram.com/p/album_12/",
        message=message,
        status_messenger=status_messenger,
        settings=settings,
    )

    assert result is True
    # 12 items -> batch of 10 and batch of 2: both >= 2, so reply_media_group called twice
    assert message.reply_media_group.call_count == 2
    first_call_media = message.reply_media_group.call_args_list[0].kwargs["media"]
    second_call_media = message.reply_media_group.call_args_list[1].kwargs["media"]
    assert len(first_call_media) == 10
    assert len(second_call_media) == 2


@pytest.mark.asyncio
@patch("app.media.gallery_dl.run_blocking")
async def test_gallery_dl_incomplete_album_tracking(
    mock_run, tmp_path: Path, settings, temp_db
):
    await init_db(temp_db)

    status_messenger = MagicMock(spec=StatusMessenger)
    status_messenger.edit_message = AsyncMock()
    status_messenger.delete_status_message = AsyncMock()

    message = AsyncMock()
    message.chat_id = 777
    message.from_user = MagicMock(id=888, username="david", first_name="David")

    # Post had 6 photos, but only 2 downloaded
    async def fake_run(func, *args, **kwargs):
        temp_dir = args[1]
        for i in (1, 2):
            img = temp_dir / f"{i:02d}.jpg"
            img.write_bytes(b"photo bytes")
            info = temp_dir / f"{i:02d}.jpg.json"
            info.write_text(f'{{"count": 6, "num": {i}}}', encoding="utf-8")

    mock_run.side_effect = fake_run

    result = await download_and_send_with_gallery_dl(
        url="https://instagram.com/p/incomplete_album/",
        message=message,
        status_messenger=status_messenger,
        settings=settings,
    )

    assert result is True
    message.reply_media_group.assert_called_once()

    # Check that incomplete_album was recorded in database
    issues = await get_recent_download_issues(temp_db, chat_id=777)
    assert len(issues) == 1
    assert issues[0].issue_type == "incomplete_album"
    assert issues[0].total_items == 6
    assert issues[0].downloaded_items == 2
    assert issues[0].first_name == "David"


@pytest.mark.asyncio
async def test_handle_download_issues_empty(settings, temp_db):
    await init_db(temp_db)
    update = MagicMock()
    update.effective_chat.id = 555
    update.message = AsyncMock()
    context = MagicMock()
    context.application.settings = {"app_settings": settings}

    await handle_download_issues(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "Clean record" in reply_text


@pytest.mark.asyncio
async def test_handle_download_issues_with_failures(settings, temp_db):
    await init_db(temp_db)
    await record_download_issue(
        db_path=temp_db,
        chat_id=555,
        url="https://instagram.com/p/fail/",
        issue_type="incomplete_album",
        error_message="Only got 2 of 5",
        total_items=5,
        downloaded_items=2,
        first_name="Frank",
    )

    update = MagicMock()
    update.effective_chat.id = 555
    update.message = AsyncMock()
    context = MagicMock()
    context.application.settings = {"app_settings": settings}

    await handle_download_issues(update, context)

    update.message.reply_text.assert_called_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "[Incomplete Album]" in reply_text
    assert "Frank" in reply_text
    assert "2 of 5" in reply_text
    assert "@gork open issue" in reply_text
