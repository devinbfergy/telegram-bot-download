# Issue #12: Fix TikTok Video Processing

**Issue**: TikTok video at `https://www.tiktok.com/t/ZThwtJ8cX` not processing correctly

**Root Cause Analysis**: The current implementation has the following potential issues:
1. Generic TikTok detection uses simple string matching (`"tiktok" in url`) which may miss shortened URLs
2. No TikTok-specific error messages to help users understand what went wrong
3. No dedicated TikTok profile in yt-dlp profiles (uses default profile)
4. Limited logging for TikTok-specific failures
5. No handling for TikTok's short URL format (`tiktok.com/t/XXXXX`)

**Solution**: Enhance TikTok URL detection, add TikTok-specific error handling, and improve logging.

---

## Tasks

- [ ] Add TikTok short URL pattern detection to `app/media/detectors.py`: Create a new function `is_tiktok_url()` that detects both regular TikTok video URLs (`tiktok.com/@user/video/123`) and short URLs (`tiktok.com/t/XXXXX`). Update the existing `TIKTOK_PHOTO_PATTERN` logic to be part of a more comprehensive TikTok detection system.

- [ ] Add TikTok-specific profile to `app/media/ytdlp_profiles.py`: Create a new `tiktok` profile with optimized settings for TikTok videos including format selection, cookies handling, and user-agent configuration. This should use the same format selection strategy as the default profile but with TikTok-specific options.

- [ ] Update downloader to use TikTok profile in `app/media/downloader.py`: Modify the auto-detection logic in `download_and_send_media()` method (around line 50-60) to detect TikTok URLs using the new `is_tiktok_url()` function and select the `tiktok` profile. Add this detection before the existing shorts/instagram checks.

- [ ] Add TikTok-specific error messages to `app/config/strings.py`: Add new message keys: `tiktok_processing`, `tiktok_error_generic`, `tiktok_error_unavailable`, `tiktok_error_private`, and `tiktok_short_url_detected`. These will provide better user feedback for TikTok-specific failures.

- [ ] Enhance error handling for TikTok in `app/media/downloader.py`: In the exception handlers (lines 192-224), add specific handling for TikTok URLs that provides better error messages. Check the exception message for TikTok-specific errors like "Video unavailable", "Private video", or "Content not available" and return appropriate user-facing messages. Add debug logging to capture the full yt-dlp error for TikTok URLs.

- [ ] Update handler detection logic in `app/telegram_bot/handlers.py`: Replace the simple string check `or "tiktok" in url` (line 62) with the new `is_tiktok_url()` function call to properly handle short URLs and edge cases. Ensure the TikTok photo URL check happens first to maintain existing behavior.

- [ ] Add comprehensive logging for TikTok processing in `app/media/downloader.py`: Add INFO-level logs when TikTok URL is detected, DEBUG-level logs for yt-dlp options being used, and WARNING-level logs for TikTok-specific extraction failures. This will help diagnose future TikTok issues.

- [ ] Update tests in `app/tests/test_detectors.py`: Add test cases for the new `is_tiktok_url()` function covering regular video URLs, short URLs (like `tiktok.com/t/XXXXX`), photo URLs, and invalid URLs. Ensure existing TikTok photo detection tests still pass.

- [ ] Add integration test for TikTok URL processing in `app/tests/test_downloader.py`: Create a test that verifies TikTok short URLs are properly detected and routed to the TikTok profile. Mock the yt-dlp download to ensure the correct profile options are passed.

- [ ] Test the fix with the reported URL: Manually test the bot with `https://www.tiktok.com/t/ZThwtJ8cX` to verify it processes correctly. Check logs for proper detection, profile selection, and any error messages. Document the results in the GitHub issue.

---

## Testing Checklist

After completing the above tasks, verify:

- Regular TikTok video URLs are detected correctly
- TikTok short URLs (`/t/XXXXX`) are detected and processed
- TikTok photo/slideshow URLs still work as before
- Error messages are specific and helpful for TikTok failures
- Logs contain sufficient detail to diagnose issues
- All unit tests pass (`uv run pytest -v`)
- The specific URL from issue #12 now processes successfully

---

## Notes

- The TikTok short URL format (`tiktok.com/t/XXXXX`) is a redirect that may require yt-dlp to follow redirects
- Some TikTok videos may require cookies or specific user-agent strings to download
- Gallery-dl fallback should still work if yt-dlp fails completely
- Consider adding rate limiting detection if TikTok starts blocking requests
