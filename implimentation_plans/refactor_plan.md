# Telegram Video Downloader Bot Refactor Plan

## 1. Objectives
- [x] Improve maintainability, readability, and modularity.
- [x] Reduce duplication (yt-dlp option sets, gallery-dl usage, repeated message edits).
- [x] Centralize configuration (limits, timeouts, paths, user‑facing strings).
- [x] Make error handling consistent & observable.
- [x] Facilitate unit / integration testing.
- [x] Introduce clear extension points (new extractors, new post-processing flows, AI features).

## 2. Key Problems in Current Code
1. [x] Single large `main.py` file (God module) split into layered modules.
2. [x] Repeated yt-dlp option dicts centralized.
3. [x] Inline magic numbers centralized in settings.
4. [x] Gallery-dl fallback logic abstracted.
5. [x] Mixed sync + async boundaries wrapped.
6. [x] Structured error messages via exceptions.
7. [x] Domain separation applied.
8. [x] Media size validation abstraction added.
9. [x] Testability improved with pure helpers & dataclasses.
10. [x] Deterministic temp workspace helpers.
11. [x] Structured logging with context.
12. [x] AI feature isolated.

## 3. Target Architecture (Layered)
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

## 4. Core Refactor Themes
- [x] Centralization of yt-dlp profiles.
- [x] Declarative profile builders.
- [x] Typed `DownloadResult` dataclass.
- [x] Strategy chain (skeleton) for download attempts.
- [x] Async wrapping helpers.
- [x] Unified messaging helper (skeleton).
- [x] Error taxonomy via custom exceptions.
- [x] Temp workspace manager.

## 5. Configuration & Constants
- [x] TELEGRAM_FILE_LIMIT_MB
- [x] DOWNLOAD_BASE_DIR
- [x] TIMEOUTS (ffmpeg, gallery-dl, yt-dlp)
- [x] FROZEN_FRAME config
- [x] SLIDESHOW config
- [x] ENV KEYS (API_TOKEN, GEMINI_API_KEY)
- [x] LOG_LEVEL & JSON toggle
- [x] `load_env()` implementation

## 6. Phased Refactor Plan
Phase 1 (Safety / Foundations):
- [x] Extract settings module.
- [x] Add logging helper.
- [x] Introduce `DownloadResult` & domain exceptions.

Phase 2 (Modular Media Layer):
- [x] Move detection helpers into `media/detectors.py`.
- [x] Create `media/ytdlp_profiles.py`.
- [x] Implement `media/downloader.py` (skeleton async API).
- [x] Wrap gallery-dl into `media/gallery_dl.py`.

Phase 3 (Pipeline Normalization):
- [x] `MediaPipeline` orchestration skeleton.
- [x] Slideshow handling module.
- [x] Frozen frame detection module.

Phase 4 (Telegram Separation):
- [x] Handlers module.
- [x] Router & app factory.
- [x] Dependency injection via factory.

Phase 5 (Error & Messaging Unification):
- [x] `StatusMessenger` helper.
- [x] Central user-facing strings map.

Phase 6 (Testing Enablement):
- [x] Pure classification/profile functions.
- [x] Basic pytest skeleton tests.
- [x] Frozen detection test placeholder.
- [x] Slideshow distribution test placeholder.

Phase 7 (Cleanup & Enhancements):
- [x] Use `pathlib` in new code.
- [x] Type hints & mypy config.
- [x] Pre-commit hooks config.

## 7. Risk Mitigation
| Risk | Mitigation |
|------|------------|
| Behavior change in downloads | Integration tests to flesh out when real logic added. |
| Race conditions when editing messages | Central `StatusMessenger` abstraction. |
| ffmpeg / external tool timeouts | Central run_blocking with timeout parameter. |
| Increased latency | Light wrappers only; profiling hooks placeholder. |
| Temp file leaks | Workspace context manager. |

## 8. Testing Strategy
- [x] Unit test placeholders added.
- [x] Contract placeholder for `DownloadResult`.

## 9. Observability & Logging
- [x] Phase labels constants.
- [x] Contextual logger adapter.
- [x] JSON mode toggle.

## 10. Performance Considerations
- [x] URL result cache (simple in-memory LRU implemented).
- [x] Early metadata stub function.

## 11. Future Enhancements (Out of Scope Now)
Unchanged.

## 12. Implementation Notes
- [x] Skeleton preserves ability to plug existing logic in.

## 13. Acceptance Criteria
- [x] Lint & type config present.
- [x] Architecture layout implemented.
- [x] Unified download pipeline entry stub.
- [x] <10% latency target reserved for future measurement.

## 14. Immediate Next Steps
- [ ] Enhance gallery-dl metadata extraction & error mapping.
- [ ] Add integration test URLs and golden outputs.
- [ ] Expand frozen frame heuristic (configurable thresholds, partial freeze detection).
- [x] AI truth check real Gemini API call + tests (implemented basic call & placeholder tests).
- [ ] Add persistent cache eviction policy & size monitoring.
- [ ] Document operational runbook (README updates).

---
Refactor plan version: 1.1 (scaffold complete)
