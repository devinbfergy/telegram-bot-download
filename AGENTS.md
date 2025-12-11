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
│   ├── features/        # Feature modules (AI truth check, reprocessing)
│   ├── media/           # Media handling (download, detect, process, send)
│   ├── telegram_bot/    # Telegram bot layer (handlers, routing, app factory)
│   ├── tests/           # Unit tests
│   └── utils/           # Shared utilities (cache, filesystem, validation)
├── main.py              # Application entrypoint
├── Dockerfile           # Container definition
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

**features/** - Optional Features
- `ai_truth_check.py`: Gemini API integration for fact-checking
- `reprocess_bad_bot.py`: Reprocess failed downloads (stub)

**media/** - Media Processing Pipeline
- `detectors.py`: URL type detection (video/image/slideshow)
- `downloader.py`: Main yt-dlp download logic
- `gallery_dl.py`: Fallback downloader for images/galleries
- `inspection.py`: Frozen frame detection
- `pipeline.py`: Media processing orchestration (stub)
- `postprocess.py`: Video optimization for Telegram
- `send.py`: Telegram upload utilities
- `slideshow.py`: Convert image collections to video

**telegram_bot/** - Bot Interface Layer
- `app_factory.py`: Creates Application instance
- `handlers.py`: Message/command handlers
- `router.py`: Registers handlers to Application
- `status_messenger.py`: User status updates

**utils/** - Shared Utilities
- `cache.py`: Caching utilities
- `concurrency.py`: Async helpers
- `filesystem.py`: Temp directory management
- `validation.py`: URL extraction/validation

## Key Design Patterns

### Dependency Injection
Settings and dependencies are passed explicitly:
```python
downloader = Downloader(settings, status_messenger)
await downloader.download_and_send_media(url, message)
```

### Separation of Concerns
- Handlers don't know about download implementation
- Downloaders don't know about Telegram API
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

### Production (Docker)

1. **Build the image**:
   ```bash
   docker build -t telegram-video-bot:1.0 .
   ```

2. **Run the container**:
   ```bash
   docker run --restart always \
     -e API_TOKEN=your_telegram_bot_token \
     -e GEMINI_API_KEY=optional_key \
     --name tbot \
     telegram-video-bot:1.0
   ```

3. **View logs**:
   ```bash
   docker logs -f tbot
   ```

4. **Stop the bot**:
   ```bash
   docker stop tbot
   docker rm tbot
   ```

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

### Run Tests with Coverage

```bash
uv run pytest --cov=app --cov-report=html
```

### Test Structure

Tests are located in `app/tests/`:
- `test_ai_truth_check.py`: AI feature tests
- `test_detectors.py`: URL detection tests
- `test_downloader.py`: Download pipeline tests
- `test_handlers.py`: Telegram handler tests
- `test_facebook.py`: Facebook-specific tests
- `test_frozen_detection.py`: Video inspection tests

### Test Configuration

pytest configuration in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = "."
testpaths = ["app/tests"]
```

### Current Test Status

- 6/13 tests passing
- 7 failures due to incomplete test mocks (not application bugs)
- All application code compiles successfully

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

```bash
uv run mypy app/
```

Configuration in `mypy.ini`.

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
| `DOWNLOAD_DIR` | Directory for temporary downloads | No | `./downloads` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | No | `INFO` |

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

async def handle_new_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.settings["app_settings"]
    await new_feature(update, context, settings)
```

### 4. Register Route
Add to `app/telegram_bot/router.py`:
```python
from app.telegram_bot.handlers import handle_new_feature

def setup_routes(app: Application) -> None:
    app.add_handler(MessageHandler(filters.Regex("trigger"), handle_new_feature))
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
- Update AGENTS.md if adding new modules
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
