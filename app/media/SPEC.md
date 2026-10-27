---
id: media
type: module-design
status: draft
title: Media download pipeline
parent: architecture
depends-on: [utils, telegram-bot]
---

## Responsibility

This module turns a URL into media posted in the chat and reports status along the way. `Downloader`
is the entry point. `detectors` classify URLs and yt-dlp results. `ytdlp_profiles` holds the per-platform
yt-dlp options. `gallery_dl` is the fallback downloader and also handles Instagram cookies. `inspection`
detects frozen frames with OpenCV, and `slideshow` builds a video from images with FFmpeg.

## Pipeline

1. Pick a profile from the URL (`shorts`, `instagram`, `tiktok`, or `default`). Callers can force one;
   `bad bot` uses `telegram`. For Instagram, attach a cookie file. A mounted `INSTAGRAM_COOKIE_FILE`
   takes precedence over a cookie file built from `INSTAGRAM_SESSIONID`.
2. Run yt-dlp in a temp dir. If the result is a slideshow, hand off to gallery-dl.
3. If the video is frozen, retry with the `fallback` profile. If that video is also frozen, hand off
   to gallery-dl.
4. Enforce the size limit (`telegram_max_video_size`, 50 MB). Reply with the video. The caption is a
   summarized and truncated version of the source description or title.
5. Any yt-dlp `DownloadError` or `ExtractionFailed` also falls back to gallery-dl. gallery-dl sends a
   video if it finds one. Otherwise it builds a slideshow (up to 60 images), and if that fails it sends
   an album of up to 10 images.

## Boundary

- This module owns user-visible status for the whole download. It edits or deletes the status message
  and reports errors from `MESSAGES`. Callers do not report errors a second time.
- Temp directories are always cleaned up.
- yt-dlp, gallery-dl, FFmpeg, and OpenCV run in threads or subprocesses, with timeouts from
  `AppSettings.timeouts`.

## Known limitations

- Videos over 50 MB are refused with a message. They are not re-encoded or compressed to fit.
