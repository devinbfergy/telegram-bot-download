# Telegram Video Download Bot - Code Structure & Development Guide

## Overview

This is a Telegram bot application that downloads media (videos, images, audio) from various platforms using yt-dlp and gallery-dl, then sends them to Telegram chats. The application runs as a Docker container.

## Architecture

The codebase follows a modular, layered architecture:

```
telegram-bot-download/
├── app/
│   ├── config/          # Configuration & constants
│   ├── core/            # Core utilities (exceptions, logging, types)
│   ├── features/        # Feature modules (Gork AI, user memory, GitHub issues, reprocessing)
│   ├── media/           # Media handling (download, detect, process, send)
│   ├── telegram_bot/    # Telegram bot layer (handlers, routing, app factory)
│   ├── tests/           # Unit tests
│   └── utils/           # Shared utilities (cache, filesystem, validation)
├── scripts/             # Host helpers (Instagram Chrome cookie refresh)
├── secrets/             # Gitignored Netscape cookies.txt mounted into Docker
├── main.py              # Application entrypoint
├── goal-and-requirements.md  # Spec graph root (what & why)
├── architecture.md      # Spec: modules, invariants, decisions
├── Dockerfile           # Container definition
├── docker-compose.yml   # Production deployment (single service + volumes)
├── pyproject.toml       # Project metadata & dependencies
└── requirements.txt     # Legacy requirements (use pyproject.toml)
```

### Layer Responsibilities

**config/** - Centralized Configuration
- `settings.py`: All application settings (AppSettings dataclass)
- `strings.py`: User-facing messages (MESSAGES dict)
- No hardcoded values in business logic

**core/** - Foundation Components
- `exceptions.py`: Domain-specific exceptions
- `logging.py`: Structured logging setup
- `types.py`: Shared type definitions

**features/** - User-triggered Features (see `app/features/SPEC.md`)
- `mention_responder.py`: Gork replies to `@gork` / bot-handle mentions
- `ai_truth_check.py`: `@gork is this real` fact-check
- `user_memory.py`: Per-chat user memory profiles (cron job + `@gork memory`)
- `github_issue.py`: `@gork open issue` → GitHub issue
- `good_bot_catgirl.py`: `good bot` persona reply
- `reprocess_bad_bot.py`: `bad bot` reply re-downloads with the `telegram` profile

**media/** - Media Download Pipeline (see `app/media/SPEC.md`)
- `detectors.py`: URL type detection (video/image/slideshow)
- `downloader.py`: Main yt-dlp download → inspect → send logic
- `ytdlp_profiles.py`: Per-platform yt-dlp option profiles
- `gallery_dl.py`: Fallback downloader for images/galleries + Instagram cookies
- `inspection.py`: Frozen frame detection
- `slideshow.py`: Convert image collections to video

**telegram_bot/** - Bot Interface Layer
- `app_factory.py`: Creates Application instance
- `handlers.py`: Message/command handlers
- `router.py`: Registers handlers to Application
- `status_messenger.py`: User status updates

**utils/** - Shared Utilities (see `app/utils/SPEC.md`)
- `concurrency.py`: `run_blocking` async helper
- `database.py`: SQLite message store + user memories
- `filesystem.py`: Temp directory management
- `validation.py`: URL extraction/validation, caption helpers, chat allowlist

**scripts/instagram_session/** - Host-side Instagram cookie refresh (see its `SPEC.md`)

## Specs

Design intent lives in the spec graph: `goal-and-requirements.md` → `architecture.md` → a `SPEC.md`
beside each module. Specs are the ground truth for boundaries, invariants and decisions — read the
relevant one before changing behavior, and update it in the same change when you alter a contract.

## Key Design Patterns

### Dependency Injection
Settings and dependencies are passed explicitly:
```python
downloader = Downloader(settings, status_messenger)
await downloader.download_and_send_media(url, message)
```

### Separation of Concerns
- Handlers don't know about download implementation
- The media pipeline owns the whole download → send path and may use `StatusMessenger` and the Telegram `Message` directly (deliberate; see `architecture.md`)
- Configuration isolated from business logic

### Error Handling
- Custom exceptions in `core/exceptions.py`
- Structured error messages in `config/strings.py`
- Graceful degradation (yt-dlp → gallery-dl fallback)

### Status Updates
StatusMessenger provides user feedback during long operations:
```python
await status_messenger.edit_message(MESSAGES["downloading"])
# ... long operation ...
await status_messenger.edit_message(MESSAGES["uploading"])
```

## Running the Application

### Development (Local)

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Set environment variables**:
   ```bash
   export API_TOKEN="your_telegram_bot_token"
   export GEMINI_API_KEY="optional_gemini_key"  # For AI features
   ```

3. **Run the bot**:
   ```bash
   uv run main.py
   ```

### Production (Docker Compose)

Secrets go in a gitignored `.env` in the project root (see `README.md`); `docker-compose.yml` reads them.

```bash
docker compose up --build -d   # build + (re)start; data volume is preserved
docker compose logs -f         # view logs
docker compose down            # stop
docker compose down -v         # stop and wipe the SQLite volume
```

Compose mounts the named volume `bot_data` at `/data` (SQLite store) and `./secrets` read-only at
`/data/secrets` (Instagram cookies, refreshed on the host by `scripts/instagram_session/`).

### Docker Configuration

The Dockerfile:
- Uses Python 3.12 slim base image
- Installs FFmpeg (required for video processing)
- Uses `uv` package manager for fast dependency installation
- Sets `/app` as working directory
- Runs `uv run main.py` as entrypoint

## Testing

### Run All Tests

```bash
uv run pytest -v
```

### Run Specific Test File

```bash
uv run pytest app/tests/test_handlers.py -v
```

### Test Structure

Tests live in `app/tests/`, one `test_<module>.py` per module under test (detectors, downloader,
yt-dlp profiles, handlers, router, validation, filesystem, frozen detection, Instagram cookies, AI
truth check, mention responder, user memory, GitHub issue, Docker). `test_docker.py` needs a running
Docker daemon and is skipped otherwise.

### Test Configuration

pytest configuration in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = "."
testpaths = ["app/tests"]
```

### Current Test Status

- 157 passing, 5 skipped (Docker tests without a daemon)
- CI (`.github/workflows/test.yml`) runs `ruff check`, `ruff format --check` and `pytest` on pushes/PRs to `main`

### Writing Tests

Use pytest with async support:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def settings():
    return AppSettings()


@pytest.mark.asyncio
async def test_handler(settings):
    update = MagicMock()
    context = MagicMock()
    # ... test logic ...
```

## Code Quality

### Linting & Formatting

```bash
# Run ruff linter
uv run ruff check .

# Format code
uv run ruff format .
```

### Type Checking

`mypy.ini` exists, but mypy is not a project dependency; run it ad hoc:

```bash
uvx mypy app/
```

### Pre-commit Hooks

The project uses pre-commit hooks (`.pre-commit-config.yaml`):
- Ruff linting
- Trailing whitespace removal
- YAML validation
- End-of-file fixes

Install hooks:
```bash
pre-commit install
```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `API_TOKEN` | Telegram Bot API token from @BotFather | Yes | - |
| `GEMINI_API_KEY` | Google Gemini API key for AI features | No | "" |
| `APP_BASE_DIR` | Base dir; temp downloads go in `<base>/downloads` | No | cwd |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | No | `INFO` |
| `LOG_JSON` | `1` for structured JSON logs | No | `0` |
| `GITHUB_TOKEN` / `GITHUB_REPO` | Token and `owner/repo` for `@gork open issue` | No | "" |
| `ALLOWED_CHAT_IDS` | Comma-separated chat IDs served (empty = all) | No | the two group chats |
| `ADMIN_USERNAMES` / `ADMIN_USER_IDS` | Admins whose DMs are allowed | No | `megadevx` / `625304326` |
| `SQLITE_DB_PATH` | SQLite message store | No | `/data/bot_messages.db` |
| `USER_MEMORY_ENABLED` | `0` disables the memory job | No | `1` |
| `USER_MEMORY_INTERVAL_HOURS` / `USER_MEMORY_WINDOW_HOURS` | Memory job interval / message window | No | `24` / `24` |
| `INSTAGRAM_COOKIE_FILE` | Netscape cookies.txt for Instagram (compose: `/data/secrets/instagram_cookies.txt`) | No | "" |
| `INSTAGRAM_SESSIONID` | Fallback Instagram session cookie if cookies.txt is missing | No | "" |

All settings are loaded via `AppSettings` dataclass in `app/config/settings.py`.

## Adding New Features

### 1. Add Configuration
Add settings to `app/config/settings.py`:
```python
@dataclass
class AppSettings:
    new_feature_enabled: bool = field(default=False)
```

Add messages to `app/config/strings.py`:
```python
MESSAGES = {
    "new_feature_success": "✅ Feature completed!",
}
```

### 2. Create Feature Module
Create `app/features/new_feature.py`:
```python
from app.config.settings import AppSettings
from app.config.strings import MESSAGES


async def new_feature(update, context, settings: AppSettings) -> None:
    # ... implementation ...
    await update.message.reply_text(MESSAGES["new_feature_success"])
```

### 3. Add Handler
Add to `app/telegram_bot/handlers.py`:
```python
from app.features.new_feature import new_feature


async def handle_new_feature(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    settings = context.application.settings["app_settings"]
    await new_feature(update, context, settings)
```

### 4. Register Route
Add to `app/telegram_bot/router.py`:
```python
from app.telegram_bot.handlers import handle_new_feature


def register(application: Application) -> Application:
    # Group 0 is first-match-wins: add new triggers ABOVE the catch-all
    # URL handler (handlers.handle_message), or it will also fire.
    application.add_handler(
        MessageHandler(filters.TEXT & filters.Regex("trigger"), handle_new_feature)
    )
```

### 5. Write Tests
Create `app/tests/test_new_feature.py`:
```python
@pytest.mark.asyncio
async def test_new_feature(settings):
    # ... test implementation ...
```

## Debugging

### Enable Debug Logging

Set environment variable:
```bash
export LOG_LEVEL=DEBUG
uv run main.py
```

### Common Issues

**Import errors**: Ensure you're using absolute imports (`from app.module` not `from .module`)

**Test failures**: Check that mocks include all required methods/attributes

**Download failures**: Check FFmpeg installation and yt-dlp version

**Telegram upload failures**: Files over 50MB will fail (Telegram limit)

## Contributing

See `README.md` for contribution guidelines. Key points:
- Use ruff for formatting
- Write tests for new features
- Update AGENTS.md if adding new modules, and add/update the module's `SPEC.md`
- Keep configuration centralized in `config/`
- Don't hardcode strings or magic numbers

## Performance Considerations

- Downloads run in background threads (`asyncio.to_thread`)
- Temporary files cleaned up automatically
- Status updates prevent user timeout perception
- Gallery-dl fallback reduces yt-dlp failures

## Security Notes

- Never commit API tokens or keys
- Use environment variables for secrets
- Validate all user input URLs
- Limit file sizes to prevent abuse
- Run in isolated Docker container

## Support

For issues, questions, or feature requests, open a GitHub issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Log output (with tokens redacted)
