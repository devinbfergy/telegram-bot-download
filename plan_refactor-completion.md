# Telegram Video Downloader Bot - Refactor Completion Plan

**Status**: Critical blocking issues identified  
**Priority**: Fix blocking issues → Complete architecture → Add tests & CI  
**Version**: 3.0 (Corrected based on comprehensive codebase audit)

---

## Executive Summary

The refactor has made significant progress with modular architecture in place. However, **5 critical blocking issues** prevent the application from running, several items are incorrectly marked as complete, and key features remain as placeholders.

**Blocking Issues (Must Fix Immediately)**:
1. Function naming mismatch: `main.py` imports `create_app` but `app_factory.py` exports `create_application`
2. Missing filesystem utilities: `create_temp_dir()` and `safe_cleanup()` imported but not defined
3. Missing validation function: `extract_url()` doesn't exist in `utils/validation.py`
4. Wrong import locations: `handlers.py` imports detector functions from validation instead of detectors
5. Class naming mismatch: Code uses `AppSettings` but settings module defines `AppConfig`

---

## Part 1: CRITICAL BLOCKING FIXES (Must Complete First)

### 1.1 Fix Function Naming Inconsistencies

**Issue**: `main.py:5,26` imports/calls `create_app()` but `app_factory.py:10` defines `create_application()`

**Action**:
- [ ] Rename `create_application()` → `create_app()` in `app/telegram_bot/app_factory.py:10`
- [ ] Update any references to `create_application` elsewhere

**Files**: `app/telegram_bot/app_factory.py`, potentially `main.py`

---

### 1.2 Implement Missing Filesystem Utilities

**Issue**: `downloader.py:16,31,81,134` and `gallery_dl.py:13,45` import and use `create_temp_dir()` and `safe_cleanup()` but these functions don't exist in `app/utils/filesystem.py`

**Current State**: Only `temp_workspace()` and `safe_unlink()` are defined

**Action**:
- [ ] Add `create_temp_dir(prefix: str = "work_") -> Path` function
  - Should create a temporary directory and return its Path
  - Should use `tempfile.mkdtemp()` with the prefix
  - Return a `Path` object
- [ ] Add `safe_cleanup(path: Path) -> None` function
  - Should safely remove files or directories
  - Should handle missing files gracefully
  - Should handle both files and directories
  - Use `shutil.rmtree()` for dirs, `unlink()` for files

**Files**: `app/utils/filesystem.py`

**Alternative Approach** (Recommended):
- [ ] Refactor all code to use `temp_workspace()` context manager instead
- [ ] Remove imports of `create_temp_dir` and `safe_cleanup`
- [ ] Update `downloader.py` and `gallery_dl.py` to use context manager pattern

---

### 1.3 Move extract_url to Validation Module

**Issue**: `handlers.py:12` imports `extract_url` from `app.utils.validation` but function only exists in legacy `main copy.py`

**Action**:
- [ ] Copy `extract_url()` function from `main copy.py` to `app/utils/validation.py`
- [ ] Add tests for URL extraction (various formats, edge cases)
- [ ] Function signature: `def extract_url(text: str) -> str | None`
- [ ] Should handle: plain URLs, URLs in text, Markdown links, etc.

**Files**: `app/utils/validation.py`, `app/tests/test_validation.py` (new)

---

### 1.4 Fix Import Locations in Handlers

**Issue**: `handlers.py:12` imports `is_image_url, is_tiktok_photo_url, is_video_url` from `app.utils.validation` but these functions are in `app.media.detectors`

**Action**:
- [ ] Change import in `handlers.py:12` from:
  ```python
  from app.utils.validation import extract_url, is_image_url, is_tiktok_photo_url, is_video_url
  ```
  To:
  ```python
  from app.utils.validation import extract_url
  from app.media.detectors import is_image_url, is_tiktok_photo_url, is_video_url
  ```

**Files**: `app/telegram_bot/handlers.py`

---

### 1.5 Resolve Settings Class Naming

**Issue**: Settings module defines `AppConfig` class but entire codebase imports/uses `AppSettings`

**Current State**:
- `app/config/settings.py:45` defines `class AppConfig`
- `main.py:3,16` imports/uses `AppSettings`
- `handlers.py:6,33,71,85` uses `AppSettings`
- `downloader.py:10,22` uses `AppSettings`
- All tests use `AppSettings`

**Action** (Choose ONE approach):

**Option A (Recommended)**: Rename class to match usage
- [ ] Rename `class AppConfig` → `class AppSettings` in `settings.py:45`
- [ ] Update `load_config()` return type and implementation
- [ ] Keep all existing imports unchanged

**Option B**: Fix all imports
- [ ] Change all imports from `AppSettings` to `AppConfig`
- [ ] Update ~15 files across handlers, tests, features, media

**Decision**: Option A is less invasive (1 file vs 15 files)

**Files**: `app/config/settings.py`

---

### 1.6 Fix Router Handler Registration

**Issue**: `router.py:7` registers `handlers.handle_text` but function is named `handle_message` in `handlers.py:22`

**Action**:
- [ ] Change `router.py:7` from:
  ```python
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))
  ```
  To:
  ```python
  application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
  ```

**Files**: `app/telegram_bot/router.py`

---

## Part 2: COMPLETE ARCHITECTURAL REFACTORING

### 2.1 Remove Legacy Code

**Priority**: HIGH - Prevents confusion and regression

- [ ] **Delete `main copy.py`** (36KB of legacy code)
  - Contains: duplicate yt-dlp options, old handler logic, print statements
  - Last referenced by: `extract_url` function (will be migrated in 1.3)
- [ ] Verify no references to `main copy.py` remain
- [ ] Commit deletion separately with clear message

**Files**: `main copy.py` (DELETE)

---

### 2.2 Centralize All Magic Numbers

**Current Issues**:
- "50MB" hardcoded in `downloader.py:105` and `strings.py:19`
- Timeout values (120, 600, 900) scattered across code
- Sample counts and thresholds hardcoded

**Action**:
- [ ] Add to `settings.py`:
  ```python
  TELEGRAM_FILE_LIMIT_MB = 50
  TELEGRAM_UPLOAD_TIMEOUT_SECONDS = 120
  GALLERY_DL_TIMEOUT = 600
  ```
- [ ] Replace hardcoded `50 * 1024 * 1024` with `settings.telegram_max_video_size`
- [ ] Update `strings.py:19` to reference setting, not hardcode value
- [ ] Replace timeout literals in `downloader.py:115-116` with setting
- [ ] Verify `inspection.py:15,37` uses `FROZEN_FRAME` settings (appears correct)

**Files**: `app/config/settings.py`, `app/media/downloader.py`, `app/config/strings.py`

---

### 2.3 Move All User-Facing Strings to strings.py

**Current Issues**: Inline strings scattered in:
- `downloader.py:42,52,79,97,105,110,131`
- `gallery_dl.py:54,66,84,93,100,105`

**Action**:
- [ ] Add to `MESSAGES` dict in `strings.py`:
  ```python
  "downloading": "📥 Downloading...",
  "frozen_frame_retry": "⚠️ Frozen frame video detected. Retrying with fallback...",
  "frozen_frame_failed": "❌ Fallback download is also a frozen video. Aborting.",
  "video_too_large": "❌ Video is too large ({file_size_mb:.2f}MB). Limit is {limit_mb}MB.",
  "uploading": "⬆️ Uploading to Telegram...",
  "unexpected_error": "❌ An unexpected error occurred. Please try again later.",
  "gallery_dl_no_media": "❌ No media found via gallery-dl.",
  "gallery_dl_uploading_video": "⬆️ Uploading video (gallery-dl)...",
  "gallery_dl_uploading_slideshow": "⬆️ Uploading slideshow...",
  "gallery_dl_sending_images": "⬆️ Sending images (gallery-dl)...",
  "gallery_dl_no_suitable_media": "❌ No suitable media found to send.",
  "gallery_dl_error": "❌ gallery-dl error: {error}",
  "slideshow_detected": "Detected slideshow, using gallery-dl...",
  ```
- [ ] Replace all hardcoded strings in `downloader.py` with `MESSAGES[key]`
- [ ] Replace all hardcoded strings in `gallery_dl.py` with `MESSAGES[key]`
- [ ] Import `MESSAGES` from `app.config.strings` in both files

**Files**: `app/config/strings.py`, `app/media/downloader.py`, `app/media/gallery_dl.py`

---

### 2.4 Use StatusMessenger Everywhere

**Current State**: Direct bot message edits remain in:
- `downloader.py:42,52,79,97,105,110,131`
- `gallery_dl.py:54,66,84,93,100,105`

**Action**:
- [ ] Replace all `await status_messenger.edit_message()` in downloader.py to use MESSAGES
- [ ] Replace all `await status_messenger.edit_message()` in gallery_dl.py to use MESSAGES
- [ ] Verify StatusMessenger properly handles:
  - Message deletion on success
  - Error message persistence
  - Missing message edge cases
- [ ] Consider adding `edit_message_with_key(message_key: str, **format_args)` helper

**Files**: `app/media/downloader.py`, `app/media/gallery_dl.py`, `app/telegram_bot/status_messenger.py`

---

### 2.5 Replace Generic Exception Handling with Domain Exceptions

**Current Issues**: Broad `except Exception` blocks in:
- `downloader.py:127` - catches everything
- `handlers.py:50` - final fallback
- Multiple files have `except Exception: pass` or `except Exception: log`

**Action**:
- [ ] Import and use custom exceptions from `app.core.exceptions`:
  - `DownloadError` - base for all download issues
  - `UnsupportedURLError` - invalid/unsupported URLs
  - `ExtractionFailed` - yt-dlp/gallery-dl extraction failed
  - `PostProcessError` - ffmpeg/processing failures
  - `SendError` - Telegram upload failures
  - `SizeLimitExceeded` - file too large
- [ ] Update `downloader.py:122-132` to catch specific DownloadError types
- [ ] Update `gallery_dl.py:103-106` to raise `ExtractionFailed` instead of generic
- [ ] Update `handlers.py:50-54` to catch and handle domain exceptions
- [ ] Add `TimeoutError` exception for long-running operations
- [ ] Keep final `Exception` handler only for truly unexpected errors

**Files**: `app/core/exceptions.py`, `app/media/downloader.py`, `app/media/gallery_dl.py`, `app/telegram_bot/handlers.py`

---

### 2.6 Use Concurrency Wrapper Instead of Direct asyncio.to_thread

**Current Issues**: Direct `asyncio.to_thread` calls in:
- `gallery_dl.py:50,77`
- `downloader.py:45,85`

**Action**:
- [ ] Import `run_blocking` from `app.utils.concurrency` in affected files
- [ ] Replace `await asyncio.to_thread(func, args)` with `await run_blocking(func, args)`
- [ ] Benefits:
  - Centralized timeout handling (future enhancement)
  - Consistent error wrapping
  - Easier to add threadpool limits or tracing

**Files**: `app/media/gallery_dl.py`, `app/media/downloader.py`

---

### 2.7 Centralize yt-dlp Options

**Current State**:
- Modern profiles in `app/media/ytdlp_profiles.py` with 4 profiles
- Legacy duplicate options still in `main copy.py`

**Action**:
- [ ] Verify no other files contain duplicate yt-dlp option dicts
  - Check for: `ydl_opts = {`, `YoutubeDL(` with inline dicts
- [ ] After `main copy.py` is deleted (2.1), this is complete
- [ ] Document profile usage in docstrings
- [ ] Consider adding `get_profile(name: str, **overrides)` helper

**Files**: `app/media/ytdlp_profiles.py`

---

### 2.8 Complete Bad Bot Reprocessing Feature

**Current State**: `app/features/reprocess_bad_bot.py` is a 7-line placeholder with:
- Function signature `async def reprocess(url: str) -> bool`
- But `handlers.py:72` calls `await reprocess_bad_bot(update, context, settings)`
- Signature mismatch!

**Action**:
- [ ] Implement complete `reprocess_bad_bot` function:
  ```python
  async def reprocess_bad_bot(
      update: Update, 
      context: ContextTypes.DEFAULT_TYPE, 
      settings: AppSettings
  ) -> None:
      # 1. Extract URL from replied-to message
      # 2. Get 'telegram' profile from ytdlp_profiles
      # 3. Re-download with optimized settings
      # 4. Send new version
      # 5. Delete old message
  ```
- [ ] Use `ytdlp_profiles.PROFILES['telegram']` for optimized re-encoding
- [ ] Add proper error handling
- [ ] Add tests for reprocessing logic

**Files**: `app/features/reprocess_bad_bot.py`, `app/tests/test_reprocess.py` (new)

---

### 2.9 Implement Dependency Injection in MediaPipeline

**Current State**: `pipeline.py` has hard-wired module imports and direct function calls

**Issues**:
- Difficult to test in isolation
- Can't swap implementations
- No way to mock dependencies

**Action**:
- [ ] Add `__init__` method to `MediaPipeline` with dependencies:
  ```python
  def __init__(
      self,
      downloader: Downloader,
      status_messenger: StatusMessenger,
      settings: AppSettings
  ):
      self.downloader = downloader
      self.status_messenger = status_messenger
      self.settings = settings
  ```
- [ ] Replace hard-wired calls with dependency usage
- [ ] Update instantiation in handlers to pass dependencies
- [ ] Add mocked pipeline tests

**Files**: `app/media/pipeline.py`, `app/telegram_bot/handlers.py`

**Note**: This is lower priority - current hard-wired approach works for now

---

### 2.10 Consolidate Settings Structure

**Current Issues**:
- Two settings patterns: `AppConfig` dataclass and module-level constants
- `main.py` uses `AppSettings()` constructor
- `app_factory.py` uses `load_config()` function
- Inconsistent access patterns

**Action**:
- [ ] Decide on single pattern (Recommendation: Pydantic BaseSettings or dataclass)
- [ ] Consolidate all settings into single class:
  ```python
  @dataclass
  class AppSettings:
      # Telegram
      telegram_token: str
      telegram_max_video_size: int = 50 * 1024 * 1024
      telegram_upload_timeout: int = 120
      
      # API Keys
      gemini_api_key: str = ""
      ai_truth_check_enabled: bool = False
      
      # Paths
      download_base_dir: Path = field(default_factory=lambda: Path.cwd() / "downloads")
      
      # Timeouts
      ytdlp_timeout: int = 600
      gallery_dl_timeout: int = 600
      ffmpeg_timeout: int = 900
      
      # Feature flags
      frozen_frame_detection: bool = True
      slideshow_creation: bool = True
      
      # Frozen frame settings
      frozen_sample_interval: int = 15
      frozen_similarity_threshold: float = 0.995
      
      # Slideshow settings
      slideshow_frame_duration: float = 2.5
      slideshow_transition: str = "fade"
  ```
- [ ] Remove module-level constants (FROZEN_FRAME, SLIDESHOW, TIMEOUTS dicts)
- [ ] Update all references to use single settings object
- [ ] Add validation in `__post_init__`

**Files**: `app/config/settings.py`, all files using settings

---

## Part 3: TESTING & QUALITY

### 3.1 Add Missing Tests

**Current Test Coverage**:
- ✅ `test_ai_truth_check.py` - AI feature
- ✅ `test_detectors.py` - URL detection (basic)
- ✅ `test_downloader.py` - Download logic
- ✅ `test_facebook.py` - Facebook handling
- ✅ `test_frozen_detection.py` - Frozen frame detection
- ✅ `test_handlers.py` - Handler functions

**Missing Tests**:
- [ ] `test_ytdlp_profiles.py` - Profile generation
  - Test each profile builder function
  - Verify base profile is included
  - Check profile-specific options
- [ ] `test_pipeline.py` - Pipeline orchestration
  - Test cache hit/miss
  - Test slideshow creation trigger
  - Test post-processing flow
  - Test error handling
- [ ] `test_gallery_dl.py` - Gallery-dl wrapper
  - Test subprocess invocation
  - Test slideshow handling
  - Test fallback scenarios
- [ ] `test_slideshow.py` - Slideshow creation
  - Test build_slideshow with various image counts
  - Test ffmpeg invocation
- [ ] `test_validation.py` - Validation utilities (NEW after 1.3)
  - Test extract_url with various formats
  - Test validate_url
  - Test enforce_size_limit
- [ ] `test_postprocess.py` - Post-processing
  - Test ensure_mp4
  - Test normalize_audio
- [ ] `test_send.py` - Telegram sending
  - Test send_video, send_image, send_album
- [ ] `test_filesystem.py` - Filesystem utilities
  - Test temp_workspace context manager
  - Test safe cleanup
- [ ] `test_reprocess.py` - Bad bot reprocessing (after 2.8)
  - Test URL extraction from reply
  - Test reprocessing flow

**Action**:
- [ ] Create missing test files
- [ ] Aim for >80% code coverage
- [ ] Use pytest fixtures for common setups
- [ ] Mock external dependencies (yt-dlp, gallery-dl, ffmpeg, Telegram API)

**Files**: `app/tests/` (new files)

---

### 3.2 Add Test Coverage Reporting

**Action**:
- [ ] Add `pytest-cov` to requirements
- [ ] Create `pytest.ini` or update `pyproject.toml` with coverage config:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["app/tests"]
  addopts = "--cov=app --cov-report=html --cov-report=term-missing"
  ```
- [ ] Add coverage thresholds (80% minimum)
- [ ] Exclude test files from coverage

**Files**: `pyproject.toml`, `requirements.txt`

---

### 3.3 Expand Detector Tests

**Current State**: `test_detectors.py` is only 251 bytes (minimal)

**Action**:
- [ ] Add comprehensive URL pattern tests:
  - YouTube Shorts (various formats)
  - TikTok photos vs videos
  - Instagram posts, reels, stories
  - Facebook URLs
  - Direct image links
  - Edge cases and malformed URLs
- [ ] Add slideshow detection tests with mock info_dicts
- [ ] Test is_video_url with mocked yt-dlp responses

**Files**: `app/tests/test_detectors.py`

---

## Part 4: CI/CD & INFRASTRUCTURE

### 4.1 Add GitHub Actions Workflow

**Action**:
- [ ] Create `.github/workflows/ci.yml`:
  ```yaml
  name: CI
  
  on:
    push:
      branches: [main, develop]
    pull_request:
      branches: [main]
  
  jobs:
    test:
      runs-on: ubuntu-latest
      strategy:
        matrix:
          python-version: ["3.11", "3.12"]
      
      steps:
        - uses: actions/checkout@v4
        
        - name: Set up Python
          uses: actions/setup-python@v5
          with:
            python-version: ${{ matrix.python-version }}
        
        - name: Install dependencies
          run: |
            pip install -r requirements.txt
            pip install pytest pytest-cov pytest-asyncio
        
        - name: Run tests
          run: pytest
        
        - name: Check coverage
          run: pytest --cov=app --cov-fail-under=80
    
    lint:
      runs-on: ubuntu-latest
      
      steps:
        - uses: actions/checkout@v4
        
        - name: Set up Python
          uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        
        - name: Install pre-commit
          run: pip install pre-commit
        
        - name: Run pre-commit
          run: pre-commit run --all-files
    
    type-check:
      runs-on: ubuntu-latest
      
      steps:
        - uses: actions/checkout@v4
        
        - name: Set up Python
          uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        
        - name: Install mypy
          run: pip install mypy
        
        - name: Run mypy
          run: mypy app/
  ```

**Files**: `.github/workflows/ci.yml` (NEW)

---

### 4.2 Add Docker Support Improvements

**Current State**: Basic Dockerfile exists

**Action**:
- [ ] Add `.dockerignore` file
- [ ] Multi-stage build for smaller images
- [ ] Add health check endpoint
- [ ] Add docker-compose.yml for local development
- [ ] Document Docker usage in README

**Files**: `.dockerignore` (NEW), `docker-compose.yml` (NEW), `Dockerfile` (UPDATE)

---

### 4.3 Add Structured Logging

**Current State**: Basic logging only, no context

**Action**:
- [ ] Add structured logging helper in `core/logging.py`:
  ```python
  def log_with_context(logger, level, message, **context):
      """Log with structured context (chat_id, url, user_id, etc.)"""
      extra = {"context": context}
      logger.log(level, message, extra=extra)
  ```
- [ ] Add JSON log formatter (optional, for production)
- [ ] Update key log points to include context:
  - Chat ID in all handler logs
  - URL in all download logs
  - File sizes and durations
  - Error types and stack traces
- [ ] Consider using `structlog` library for production

**Files**: `app/core/logging.py`, handlers and media modules

---

## Part 5: DOCUMENTATION

### 5.1 Update README

**Action**:
- [ ] Document new architecture
- [ ] Add setup instructions
- [ ] Add configuration guide (environment variables)
- [ ] Add feature list with screenshots
- [ ] Add troubleshooting section
- [ ] Add development guide (running tests, pre-commit hooks)

**Files**: `README.md`

---

### 5.2 Add API/Module Documentation

**Action**:
- [ ] Add docstrings to all public functions
- [ ] Document expected input/output formats
- [ ] Add usage examples in docstrings
- [ ] Consider adding Sphinx documentation (optional)

**Files**: All Python files

---

### 5.3 Add Configuration Documentation

**Action**:
- [ ] Create `.env.example` file with all available settings
- [ ] Document each environment variable
- [ ] Add comments explaining feature flags
- [ ] Document default values

**Files**: `.env.example` (NEW)

---

## Execution Plan & Priority Order

### Phase 1: CRITICAL FIXES (Must do first, ~2-4 hours)
**BLOCKER - Nothing works until these are fixed**

1. ✅ Fix function naming: `create_application` → `create_app`
2. ✅ Implement `create_temp_dir()` and `safe_cleanup()` OR refactor to use `temp_workspace`
3. ✅ Move `extract_url()` to validation.py
4. ✅ Fix imports in handlers.py
5. ✅ Resolve `AppSettings` vs `AppConfig` naming
6. ✅ Fix router handler registration (`handle_text` → `handle_message`)
7. ✅ Test that bot starts and responds to basic commands

**Success Criteria**: Bot runs without import errors, responds to /start

---

### Phase 2: CLEAN UP LEGACY CODE (~1 hour)
**HIGH - Prevents confusion and technical debt**

8. ✅ Delete `main copy.py`
9. ✅ Verify no references to legacy code remain
10. ✅ Commit with clear message

**Success Criteria**: No legacy files, clean git history

---

### Phase 3: CENTRALIZE CONFIGURATION (~2-3 hours)
**HIGH - Improves maintainability**

11. ✅ Move all magic numbers to settings
12. ✅ Move all strings to MESSAGES dict
13. ✅ Consolidate settings structure (single AppSettings class)
14. ✅ Update all references

**Success Criteria**: No hardcoded strings or numbers in business logic

---

### Phase 4: IMPROVE ERROR HANDLING (~2-3 hours)
**MEDIUM - Improves reliability**

15. ✅ Use domain exceptions everywhere
16. ✅ Use concurrency wrapper instead of direct asyncio.to_thread
17. ✅ Add proper error messages for all failure modes

**Success Criteria**: Clear error messages, no generic exceptions except final fallback

---

### Phase 5: COMPLETE FEATURES (~3-4 hours)
**MEDIUM - Finish incomplete features**

18. ✅ Implement bad bot reprocessing
19. ✅ Add dependency injection to MediaPipeline (optional, can defer)
20. ✅ Complete StatusMessenger usage everywhere

**Success Criteria**: All features functional, no placeholders

---

### Phase 6: TESTING (~4-6 hours)
**MEDIUM - Ensures code quality**

21. ✅ Add missing tests (profiles, pipeline, validation, etc.)
22. ✅ Expand existing tests
23. ✅ Add coverage reporting
24. ✅ Aim for 80%+ coverage

**Success Criteria**: All modules tested, >80% coverage

---

### Phase 7: CI/CD (~2 hours)
**LOW - Automates quality checks**

25. ✅ Add GitHub Actions workflow
26. ✅ Set up automated testing
27. ✅ Add pre-commit hook enforcement

**Success Criteria**: CI runs on all PRs, blocks merges on failures

---

### Phase 8: DOCUMENTATION & POLISH (~2-3 hours)
**LOW - Improves developer experience**

28. ✅ Update README
29. ✅ Add structured logging
30. ✅ Add API documentation
31. ✅ Create .env.example

**Success Criteria**: Clear documentation, easy for new developers to onboard

---

## Estimated Total Time

- **Phase 1 (Critical)**: 2-4 hours
- **Phase 2 (Cleanup)**: 1 hour  
- **Phase 3 (Config)**: 2-3 hours
- **Phase 4 (Errors)**: 2-3 hours
- **Phase 5 (Features)**: 3-4 hours
- **Phase 6 (Tests)**: 4-6 hours
- **Phase 7 (CI/CD)**: 2 hours
- **Phase 8 (Docs)**: 2-3 hours

**Total**: ~18-26 hours of focused development work

---

## Key Risks & Mitigations

### Risk 1: Breaking Changes During Refactor
**Mitigation**: 
- Complete Phase 1 first and test thoroughly
- Each phase should leave code in working state
- Commit frequently with clear messages
- Keep `main copy.py` until Phase 1 complete (as reference)

### Risk 2: Test Writing Takes Longer Than Expected
**Mitigation**:
- Focus on critical paths first (download, send, handlers)
- Mock external dependencies aggressively
- Use existing tests as templates
- Can defer some tests to later phases

### Risk 3: Settings Consolidation Breaks Things
**Mitigation**:
- Make changes incrementally
- Update one module at a time
- Keep backward compatibility during transition
- Test after each settings change

---

## Success Metrics

### Code Quality
- [ ] No files >500 lines (currently main copy.py is 1000+ lines)
- [ ] No duplicate code blocks
- [ ] All TODOs resolved or tracked
- [ ] Type hints on all public functions

### Testing
- [ ] >80% code coverage
- [ ] All critical paths tested
- [ ] No skipped or xfail tests
- [ ] Tests run in <30 seconds

### Architecture
- [ ] Clear separation of concerns
- [ ] No circular dependencies
- [ ] Domain logic isolated from framework
- [ ] Configuration centralized

### Operations
- [ ] CI passes on all commits
- [ ] Bot starts without errors
- [ ] All features functional
- [ ] Graceful error handling

---

## Notes & Decisions

### Design Decisions Made
1. **Settings approach**: Single `AppSettings` dataclass (not BaseSettings)
2. **Temp file handling**: Use context manager pattern (`temp_workspace`)
3. **String formatting**: MESSAGES dict with `.format()` or f-strings
4. **Error handling**: Domain exceptions with final generic fallback
5. **Testing**: pytest with asyncio plugin and mocked externals

### Open Questions
1. Should we use Pydantic for settings validation?
2. Should MediaPipeline dependency injection be mandatory or optional?
3. Should we add retry logic with exponential backoff?
4. Should we add request/response logging for debugging?

### Future Enhancements (Out of Scope)
- Database for tracking downloads and user preferences
- Web dashboard for monitoring
- Multi-bot support (different tokens for different groups)
- Download queue with priority
- Advanced retry strategies
- Metrics and observability (Prometheus, Grafana)

---

## Validation Checklist

Before marking refactor complete:

### Functionality
- [ ] Bot starts without errors
- [ ] /start command works
- [ ] YouTube video download works
- [ ] YouTube Shorts download works
- [ ] TikTok photo slideshow works
- [ ] Instagram download works (via gallery-dl)
- [ ] Facebook download works (via gallery-dl)
- [ ] Frozen frame detection works
- [ ] "bad bot" reprocessing works
- [ ] "@gork is this real" AI check works
- [ ] File size limits enforced
- [ ] Timeout handling works
- [ ] Error messages are clear

### Code Quality
- [ ] No lint errors
- [ ] No type check errors
- [ ] All tests pass
- [ ] >80% code coverage
- [ ] No TODOs in code (moved to issues)
- [ ] No print statements
- [ ] No hardcoded values

### Documentation
- [ ] README up to date
- [ ] All env vars documented
- [ ] Setup instructions clear
- [ ] API docs complete

### CI/CD
- [ ] GitHub Actions workflow runs
- [ ] Tests run on PR
- [ ] Linting enforced
- [ ] Type checking enforced

---

**Plan Version**: 3.0  
**Last Updated**: Current analysis  
**Status**: Ready for execution  
**Next Action**: Begin Phase 1 - Fix Critical Blocking Issues
