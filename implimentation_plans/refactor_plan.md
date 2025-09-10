# Telegram Video Downloader Bot Refactor Plan

## 1. Objectives
- [x] Improve maintainability, readability, and modularity.
- [ ] Reduce duplication (yt-dlp option sets, gallery-dl usage, repeated message edits).
- [ ] Centralize configuration (limits, timeouts, paths, user‑facing strings).
- [ ] Make error handling consistent & observable.
- [ ] Facilitate unit / integration testing.
- [ ] Introduce clear extension points (new extractors, new post-processing flows, AI features).

## 2. Key Problems in Current Code
1. [ ] Single large `main.py` file (God module) split into layered modules.
2. [ ] Repeated yt-dlp option dicts centralized.
3. [ ] Inline magic numbers centralized in settings.
4. [ ] Gallery-dl fallback logic abstracted.
5. [ ] Mixed sync + async boundaries wrapped.
6. [ ] Structured error messages via exceptions.
7. [ ] Domain separation applied.
8. [ ] Media size validation abstraction added.
9. [ ] Testability improved with pure helpers & dataclasses.
10. [ ] Deterministic temp workspace helpers.
11. [ ] Structured logging with context.
12. [ ] AI feature isolated.

## 3. Outstanding Refactor Tasks

This section outlines the primary work remaining to complete the refactor. The goal is to migrate all logic from `main copy.py` into the target architecture defined below, and transform `main.py` into a thin entrypoint.

### A. Implement Thin Entrypoint in `main.py`
- The existing code in `main.py` must be deleted.
- It should be replaced with a simple script that:
  1. Initializes logging.
  2. Loads configuration from `app.config.settings`.
  3. Uses `app.telegram_bot.app_factory.create_app()` to build the `Application` object.
  4. Runs the application.

### B. Migrate Core Handlers
The following handlers must be moved from `main copy.py` to `app/telegram_bot/handlers.py` and adapted to use the new architecture (e.g., `StatusMessenger`, custom exceptions, media pipeline).
- `start` command handler.
- `handle_message`: The primary URL processing logic.
- `handle_bad_bot_reply`: The logic for reprocessing videos.
- `handle_gork_is_this_real`: The AI truth check feature.

### C. Migrate Media Pipeline Logic
All media-related helper functions from `main copy.py` must be moved to their respective modules in `app/media/`.
- **Detection Logic (`app/media/detectors.py`):**
  - `is_youtube_shorts_url`
  - `is_video_url`
  - `is_tiktok_photo_url`
  - `_is_slideshow_info`
  - `is_image_url`
- **Downloading Logic (`app/media/downloader.py`, `app/media/gallery_dl.py`):**
  - The core logic within `download_and_send_video`.
  - The logic for `send_via_gallery_dl`.
- **Post-processing (`app/media/postprocess.py`, `app/media/inspection.py`, `app/media/slideshow.py`):**
  - `is_frozen_frame_video`
  - `_create_slideshow_video`
- **Configuration (`app/media/ytdlp_profiles.py`):**
  - All `ydl_opts` dictionaries must be moved and centralized.

### D. Update and Improve AI Truth Check
- The `ai_truth_check` function in `app/features/ai_truth_check.py` must be updated.
- **New System Prompt:** The hardcoded prompt must be replaced with the more detailed and personality-driven prompt from `main copy.py`:
  ```
  You are a truth-telling bot named Gork. When a user asks "@gork is this real", you analyze the provided statement to determine if it is fact or fiction.

  Your reply should be:
  - Concise and direct.
  - In a sarcastic but helpful tone.
  - Start with a creative word; avoid "Well," or "Oh,".
  - Do not repeat the user's question ("@gork is this real").

  If the statement is a verifiable fact or fiction, state it clearly. If it is a subjective opinion, a joke, or something you cannot verify, frame your response as a witty or humorous observation.

  Statement to analyze: {original_text}
  ```
- **Handler Integration:** The `handle_gork_is_this_real` handler in `app/telegram_bot/handlers.py` should be the one calling this feature.

## 4. General Improvements to Implement

- **Configuration:** Ensure all magic numbers and hardcoded settings (e.g., file size limits, timeouts, output templates) are moved to `app/config/settings.py`.
- **Error Handling:** Replace all generic `try...except Exception` blocks with specific, custom exceptions defined in `app/core/exceptions.py`.
- **Status Messaging:** All `context.bot.edit_message_text` and `reply_text` calls for status updates must be routed through the `app.telegram_bot.status_messenger.StatusMessenger` to ensure consistency and prevent race conditions.
- **Testing:** For each piece of functionality migrated from `main copy.py`, corresponding unit or integration tests must be added to the `tests/` directory.

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
    reprocess_bad_bot.py   # Reprocessing logic
  telegram_bot/
    handlers.py            # Start / message / reply handlers
    router.py              # Handler registration
    app_factory.py         # Application builder
    status_messenger.py    # Safe status edit/delete
main.py                    # Thin entry point
```

---
*Refactor plan version: 2.0 (updated with outstanding tasks)*
