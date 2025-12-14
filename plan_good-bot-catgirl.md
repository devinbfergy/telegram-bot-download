# Good Bot Catgirl Feature Plan

## Objective
Add a feature where when @McClintock96 says "good bot" in a reply, the bot responds as a catgirl using Gemini AI with context from recent messages.

## Requirements
1. Detect when @McClintock96 says "good bot" (case-insensitive)
2. Fetch recent messages from the chat for context
3. Send to Gemini with a catgirl system prompt
4. Respond with a catgirl-themed message

## Implementation Steps

### 1. Add Configuration (app/config/strings.py)
- Add error messages for catgirl feature

### 2. Create Feature Module (app/features/good_bot_catgirl.py)
- Create catgirl system prompt template
- Function to fetch recent chat messages (last 5-10 messages)
- Function to call Gemini API with context
- Handle response and reply

### 3. Add Handler (app/telegram_bot/handlers.py)
- Add `handle_good_bot_reply()` function
- Check if user is @McClintock96 (username check)
- Check for "good bot" in message text

### 4. Register Route (app/telegram_bot/router.py)
- Add MessageHandler for good bot replies
- Must run before general message handler

## Technical Decisions

### User Identification
- Need to check `update.message.from_user.username == "McClintock96"`
- Case-insensitive check for "good bot"

### Context Gathering
- Use `context.bot.get_chat_history()` or similar to fetch recent messages
- Alternatively: `application.bot_data` to store recent messages
- Fallback: Just use the replied-to message if available

### System Prompt
```
You are a cute catgirl assistant. When your alpha (McClintock96) praises you with "good bot", 
you respond enthusiastically as a catgirl would. Use "nya~" occasionally, act eager to please, 
and reference any context from the recent conversation.

Recent conversation context:
{context}

Respond to being called a good bot with enthusiasm and catgirl personality!
```

## Files to Create/Modify
- [CREATE] `app/features/good_bot_catgirl.py`
- [MODIFY] `app/config/strings.py` (add messages)
- [MODIFY] `app/telegram_bot/handlers.py` (add handler)
- [MODIFY] `app/telegram_bot/router.py` (register handler)

## Testing Considerations
- Test with @McClintock96 user
- Test with other users (should not trigger)
- Test case sensitivity
- Test with/without context messages
- Test without GEMINI_API_KEY
