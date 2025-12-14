# Bad Bot Reprocessing Implementation Plan

## Goal
Implement the "bad bot" feature that allows users to reply to a bot's video message with "bad bot" to trigger a reprocessing with better quality settings.

## Current State
- Handler infrastructure exists in `handlers.py:78-105`
- Handler is registered in `router.py:35-40`
- Trigger detection works (any reply containing "bad bot")
- Stub function exists in `features/reprocess_bad_bot.py`
- Telegram optimization profile exists in `ytdlp_profiles.py:177-218`

## Implementation Steps

### 1. Extract URL from replied message
- Check if replied message is from the bot (optional - decide if we care)
- Extract URL from the message text (use `validation.extract_url()`)
- Handle case where no URL is found

### 2. Download with "telegram" profile
- Use the existing Downloader class but with the "telegram" profile
- The telegram profile:
  - Limits height to 720p
  - Uses CRF 26 (better quality than default CRF 28)
  - Scales to max width 720px
  - Uses same postprocessing as default

### 3. Send the reprocessed video
- Reply to the original message with the new video
- Update status messages during the process
- Handle errors gracefully

### 4. Add status messages
- Add messages to `config/strings.py`:
  - "reprocessing": "🔄 Reprocessing with better quality..."
  - "reprocessing_no_url": "❌ Could not find URL in the original message."
  - "reprocessing_complete": "✅ Reprocessed video with better quality!"

## Design Decisions
- Reuse existing Downloader class with telegram profile
- Extract URL from original message text (not from caption or entities)
- Don't validate that replied message is from bot (keep it simple)
- Use existing error handling infrastructure

## Questions to Consider
- Should we check that the replied message is actually from the bot?
- Should we delete the old video? (No - keep history)
- Should we add a cooldown to prevent abuse? (Not initially)
