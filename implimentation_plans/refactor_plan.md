# Telegram Video Downloader Bot Refactor Plan

## 1. Objectives
- [x] Improve maintainability, readability, and modularity.
- [ ] Reduce duplication (yt-dlp option sets, gallery-dl usage, repeated message edits).
- [x] Centralize configuration (limits, timeouts, paths, user‑facing strings) (partial; further consolidation needed).
- [ ] Make error handling consistent & observable.
- [x] Facilitate unit / integration testing (initial tests present).
- [ ] Introduce clear extension points (new extractors, new post-processing flows, AI features) (pipeline partly present).

## 2. Key Problems in Current Code
1. [ ] Single large `main.py` file (God module) split into layered modules (legacy `main copy.py` still present; new entrypoint incomplete).
2. [ ] Repeated yt-dlp option dicts centralized (legacy copies remain in `main copy.py`).
3. [ ] Inline magic numbers centralized in settings (50MB & others still inline in several modules).
4. [ ] Gallery-dl fallback logic abstracted (partial; wrapper exists, legacy logic duplicated elsewhere).
5. [ ] Mixed sync + async boundaries wrapped (direct `asyncio.to_thread` / subprocess calls remain scattered).
6. [ ] Structured error messages via exceptions (exceptions module unused in most paths).
7. [ ] Domain separation applied (partial; leakage & legacy file remain).
8. [ ] Media size validation abstraction added (partial; direct size checks still present).
9. [x] Testability improved with pure helpers & dataclasses (tests + dataclasses present; expansion needed).
10. [ ] Deterministic temp workspace helpers (helper exists; inconsistent usage & missing `create_temp_dir`).
11. [ ] Structured logging with context (basic logging only).
12. [x] AI feature isolated (feature module + tests).

## 3. Outstanding Refactor Tasks

### A. Implement Thin Entrypoint in `main.py`
- [ ] Delete existing monolithic logic from `main.py` (legacy file still exists as `main copy.py`).
- [ ] Import and initialize logging via `app.core.logging`.
- [ ] Load configuration from `app.config.settings`.
- [ ] Create application with `app.telegram_bot.app_factory.create_app()` (function naming mismatch: `create_application`).
- [ ] Run the application (async `application.run_polling()` or equivalent).
- [ ] Ensure no business logic remains in entrypoint.

### B. Migrate Core Handlers to `app/telegram_bot/handlers.py`
- [x] Move and adapt `start` handler.
- [x] Move and adapt `handle_message` (URL processing pipeline integration pending).
- [x] Move and adapt `handle_bad_bot_reply` (logic still placeholder in feature module).
- [x] Move and adapt `handle_gork_is_this_real`.
- [ ] Replace direct bot edits with `StatusMessenger` (only applied in main message flow).
- [ ] Replace broad `except Exception` with custom exceptions.
- [x] Ensure handlers only orchestrate (download logic delegated).
- [x] Add tests for each handler (present in tests).

### C. Migrate Media Pipeline Logic

#### Detectors (`app/media/detectors.py`)
- [x] `is_youtube_shorts_url`
- [x] `is_video_url`
- [x] `is_tiktok_photo_url`
- [ ] `_is_slideshow_info` (implemented as `is_slideshow` but naming / coverage differs).
- [x] `is_image_url`

#### Downloading (`app/media/downloader.py`, `app/media/gallery_dl.py`)
- [x] Extract core of `download_and_send_video` into downloader abstraction.
- [x] Implement gallery-dl wrapper in `gallery_dl.py`.
- [x] Implement fallback sequencing (yt-dlp -> gallery-dl -> failure).
- [ ] Centralize temp workspace & cleanup logic (mixed helpers; missing unified temp dir creator).
- [ ] Move retry / transient error handling (no structured retry logic yet).

#### Post-processing (`app/media/postprocess.py`, `app/media/inspection.py`, `app/media/slideshow.py`)
- [x] `is_frozen_frame_video` -> `inspection.py` (as `detect_frozen_frames`).
- [x] `_create_slideshow_video` -> slideshow module (different function names; integration gaps remain).
- [x] Normalization / transcoding steps -> `postprocess.py` (basic ensure & normalize functions).
- [ ] Deduplicate ffmpeg invocation helpers (ffmpeg still called ad-hoc in multiple modules).

#### Configuration (`app/media/ytdlp_profiles.py`)
- [ ] Move all `ydl_opts` dict variants (legacy copies persist in `main copy.py`).
- [x] Provide builder functions (profile getter functions present).
- [ ] Remove inline option dict duplication from handlers / legacy code.
- [ ] Add tests for profile builders.

#### Pipeline Orchestration (`app/media/pipeline.py`)
- [x] Introduce `MediaPipeline` coordinating detection -> download -> post-process -> send.
- [ ] Inject dependencies (downloader, postprocessor, messenger) for testability (currently hard-wired module calls).
- [x] Surface structured result / errors (uses `DownloadResult`).

### D. Update and Improve AI Truth Check (`app/features/ai_truth_check.py`)
- [x] Replace legacy prompt with new detailed Gork system prompt.
- [x] Parameterize original user text (`{original_text}`).
- [ ] Add timeout / error handling with custom exception (generic errors only).
- [x] Ensure `handle_gork_is_this_real` invokes updated function.
- [x] Add unit test with mocked AI backend.
- [x] Add guard for empty / non-analyzable content.

## 4. General Improvements to Implement
- [ ] Centralize all magic numbers & limits in `settings.py` (partial; many literals remain: 50MB, timeouts, counts).
- [ ] Move user-facing strings to `strings.py` (partial; several inline messages remain in downloader, gallery, handlers).
- [ ] Replace generic `try/except` with domain exceptions in `app/core/exceptions.py`.
- [ ] Implement `StatusMessenger` in all status update paths (mixed direct bot calls remain).
- [ ] Add structured logging context (chat id, url) via helpers (only basic logging used).
- [ ] Introduce filesystem utilities for deterministic temp dirs (helper exists; inconsistent usage & missing create function referenced elsewhere).
- [ ] Add validation utilities for media size & type (partial; size & URL validators only).
- [ ] Async boundary wrappers consolidated in `utils/concurrency.py` (direct `asyncio.to_thread` scattered).
- [ ] Ensure no direct `print()` calls remain (`main copy.py` still prints).
- [ ] Coverage: add tests for detectors, profiles, pipeline, AI feature (profiles & pipeline tests missing).
- [ ] CI integration (lint + tests) (pre-commit only; no CI workflow).

## 5. Target Architecture (Layered)
```
app/
  config/
    settings.py            # Constants / env loading
    strings.py             # User-facing text
  core/
    logging.py             # Logging setup / helpers
    exceptions.py          # Domain-specific exceptions
    types.py               # Typed dataclasses / enums
  utils/
    filesystem.py          # Temp dirs, safe delete
    validation.py          # Size checks, URL classification
    concurrency.py         # run_blocking wrappers
  media/
    detectors.py           # is_video_url, is_image_url, slideshow detection
    ytdlp_profiles.py      # Centralized yt-dlp option builders
    downloader.py          # Unified download interface
    gallery_dl.py          # Wrapper for gallery-dl operations
    slideshow.py           # Slideshow assembly
    inspection.py          # Frozen frame detection
    postprocess.py         # Transcoding / normalization steps
    send.py                # Telegram sending utilities (videos, images, albums)
    pipeline.py            # MediaPipeline orchestration
  features/
    ai_truth_check.py      # Gemini integration
    reprocess_bad_bot.py   # Reprocessing logic (placeholder)
  telegram_bot/
    handlers.py            # Start / message / reply handlers
    router.py              # Handler registration
    app_factory.py         # Application builder
    status_messenger.py    # Safe status edit/delete
main.py                    # Thin entry point (incomplete)
```

### 5a. Module Existence Checklist
- [x] config/settings.py
- [x] config/strings.py
- [x] core/logging.py
- [x] core/exceptions.py
- [x] core/types.py
- [x] utils/filesystem.py
- [x] utils/validation.py
- [x] utils/concurrency.py
- [x] media/detectors.py
- [x] media/ytdlp_profiles.py
- [x] media/downloader.py
- [x] media/gallery_dl.py
- [x] media/slideshow.py
- [x] media/inspection.py
- [x] media/postprocess.py
- [x] media/send.py
- [x] media/pipeline.py
- [x] features/ai_truth_check.py
- [x] features/reprocess_bad_bot.py
- [x] telegram_bot/handlers.py
- [x] telegram_bot/router.py
- [x] telegram_bot/app_factory.py
- [x] telegram_bot/status_messenger.py
- [x] main.py (refactored thin entrypoint) (needs correction + legacy file removal)

## 6. Progress Summary
Core scaffolding (modules, basic tests, pipeline, profiles, AI feature) is in place. Remaining high-impact gaps:
- Remove / absorb `main copy.py` and finalize thin `main.py` using `create_application` (or align naming).
- Consolidate temp dir utilities (implement and standardize `create_temp_dir`).
- Eliminate duplicated yt-dlp option dicts & migrate remaining logic to profiles.
- Expand StatusMessenger usage & replace inline strings with `MESSAGES`.
- Introduce structured exception usage & targeted retries.
- Add tests for pipeline orchestration & profile builders.
- Implement dependency injection in `MediaPipeline` for easier testing.
- Remove magic numbers (50MB, sample counts) from code into settings.
- Add CI workflow (GitHub Actions) for lint + test.

---
Refactor plan version: 2.2 (status updated)
