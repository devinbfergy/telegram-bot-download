# Phase 4: Improve Error Handling - Implementation Plan

## Objectives
1. Replace generic `Exception` catches with domain exceptions from `app.core.exceptions`
2. Use `run_blocking` wrapper instead of direct `asyncio.to_thread`
3. Add structured error responses
4. Implement proper exception hierarchy usage

## Current State Analysis

### Exceptions Available (app/core/exceptions.py)
```python
class DownloadError(Exception)          # Base download error
class UnsupportedURLError(DownloadError)
class ExtractionFailed(DownloadError)
class PostProcessError(DownloadError)
class SendError(DownloadError)
class SizeLimitExceeded(DownloadError)
```

### Issues Found

#### 1. StatusMessenger Interface Mismatch
**Problem**: Code expects methods that don't exist in StatusMessenger class.

**Expected Methods** (used in code):
- `edit_message(text)` - used in downloader.py, gallery_dl.py
- `send_message(text)` - used in handlers.py
- `delete_status_message()` - used in downloader.py, handlers.py
- `has_active_message()` - used in handlers.py

**Actual Methods** (in status_messenger.py):
- `send_or_edit(context, text)`
- `finalize(delete=bool)`

**Also**: Constructor mismatch:
- handlers.py creates: `StatusMessenger(bot=..., chat_id=..., settings=...)`
- status_messenger.py only accepts: `StatusMessenger(chat_id)`

**Resolution**: Need to update StatusMessenger class to match expected interface OR update all callers. For Phase 4, we'll note this as a prerequisite fix.

#### 2. asyncio.to_thread Usage
Files using `asyncio.to_thread` directly:
- `app/media/downloader.py` (lines 46, 86)
- `app/media/gallery_dl.py` (lines 51, 78)

Should use `run_blocking` from `app/utils/concurrency.py` instead.

#### 3. Generic Exception Handling
Files with broad `except Exception` catches:
- `app/media/downloader.py` (line 131) - should catch specific exceptions
- `app/media/gallery_dl.py` (line 104) - should catch specific exceptions  
- `app/telegram_bot/handlers.py` (line 51) - final fallback, okay
- `app/features/ai_truth_check.py` (line 89) - should be more specific
- `app/media/slideshow.py` (line 125) - should be more specific
- `app/utils/filesystem.py` (lines 25, 31) - cleanup operations, okay
- `app/media/inspection.py` (lines 7, 12, 47) - import/optional deps, okay
- `app/media/pipeline.py` - multiple, needs review
- `app/media/send.py` - multiple, needs review
- `app/telegram_bot/status_messenger.py` (lines 18, 25) - defensive, okay
- `app/media/postprocess.py` (lines 16, 25) - defensive, okay
- `app/media/detectors.py` (line 75) - defensive, okay

## Implementation Plan

### Step 1: Fix StatusMessenger Interface (Prerequisite)
Update `app/telegram_bot/status_messenger.py` to match expected interface:
```python
class StatusMessenger:
    def __init__(self, bot, chat_id: int, settings: AppSettings):
        self.bot = bot
        self.chat_id = chat_id
        self.settings = settings
        self._message = None
    
    async def send_message(self, text: str):
        """Send initial status message"""
        
    async def edit_message(self, text: str):
        """Edit existing status message or send if none exists"""
        
    async def delete_status_message(self):
        """Delete the status message if it exists"""
        
    def has_active_message(self) -> bool:
        """Check if there's an active status message"""
        return self._message is not None
```

### Step 2: Update downloader.py
1. Add import: `from app.utils.concurrency import run_blocking`
2. Replace `asyncio.to_thread` with `run_blocking` (2 occurrences)
3. Add imports for domain exceptions: `ExtractionFailed`, `SizeLimitExceeded`
4. Import yt-dlp's DownloadError as `YtDlpDownloadError` to distinguish
5. Update exception handling:
   - Catch `YtDlpDownloadError` specifically for yt-dlp failures
   - Catch `ExtractionFailed` for extraction issues
   - Catch `SizeLimitExceeded` for file size violations
   - Catch `FileNotFoundError` separately
   - Keep generic `Exception` as final fallback

### Step 3: Update gallery_dl.py
1. Add import: `from app.utils.concurrency import run_blocking`
2. Replace `asyncio.to_thread` with `run_blocking` (2 occurrences)
3. Add imports for domain exceptions
4. Update exception handling to catch specific errors:
   - Subprocess errors
   - File not found errors
   - Keep generic `Exception` as final fallback

### Step 4: Update handlers.py
Exception handling here is acceptable as final fallback. Main change:
- Ensure proper logging of unexpected errors
- Use domain exceptions if we add handler-specific errors

### Step 5: Update ai_truth_check.py
1. Add domain exception for AI errors (optional - could add `AIError` to exceptions.py)
2. Catch specific exceptions:
   - API connection errors
   - Timeout errors
   - Authentication errors
3. Keep generic Exception as final fallback with better logging

### Step 6: Update slideshow.py
1. Add domain exception imports
2. Catch specific FFmpeg errors
3. Add better error messages

### Step 7: Testing
- Run all tests to ensure no regressions
- Verify error messages are appropriate
- Check that fallback paths still work

## Success Criteria
- [ ] No direct `asyncio.to_thread` calls in business logic (downloader, gallery_dl)
- [ ] Domain exceptions used where appropriate
- [ ] Better error messages for users
- [ ] Fallback mechanisms still work
- [ ] All tests pass
- [ ] No loss of functionality

## Notes
- StatusMessenger interface fix is critical and blocks other changes
- Some generic exception handlers are appropriate (cleanup, defensive coding)
- Focus on user-facing error paths first (downloader, gallery_dl)
- Pipeline and send modules need separate review (out of scope for initial phase 4)
