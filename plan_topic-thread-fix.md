# Plan: Fix Bot Response in Topic Channels

## Problem
The bot doesn't respond correctly to messages in Telegram group topics (forum channels). It only works in the main "General" channel because status messages don't include the `message_thread_id` parameter.

## Root Cause
1. `StatusMessenger` only stores `chat_id` but not `message_thread_id`
2. When sending/editing status messages, it uses `bot.send_message()` and `bot.edit_message_text()` without the `message_thread_id` parameter
3. The `message.reply_video()` call in downloader.py correctly uses thread ID (it's automatic with reply methods), but status messages don't

## Solution
1. Update `StatusMessenger.__init__()` to accept and store `message_thread_id` (optional)
2. Pass `message_thread_id` in `send_message()` and `edit_message()` calls
3. Extract `message_thread_id` from the update in `handle_message()` and pass to StatusMessenger
4. Do the same for other handlers that use StatusMessenger

## Implementation Steps
1. Modify `app/telegram_bot/status_messenger.py`:
   - Add `message_thread_id` parameter to `__init__`
   - Store it as instance variable
   - Pass it to `send_message()` and `edit_message_text()` calls

2. Modify `app/telegram_bot/handlers.py`:
   - Extract `message_thread_id` from `update.message` or `update.effective_message`
   - Pass it when creating StatusMessenger instances

## Telegram API Context
- In forum groups (supergroups with topics enabled), each topic has a unique `message_thread_id`
- If not specified, messages default to the "General" topic
- The thread ID is available via `message.message_thread_id` or `message.reply_to_message.message_thread_id`
- Bot API methods that support this: `send_message`, `edit_message_text`, `send_video`, `send_photo`, etc.
