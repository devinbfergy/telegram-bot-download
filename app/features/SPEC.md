---
id: features
type: module-design
status: draft
title: Features (Gork AI & reprocessing)
parent: architecture
depends-on: [media, utils]
---

## Responsibility

These are the user-triggered behaviors beyond plain downloading. Each feature is one async entry point,
`(update, context, settings)`, that a handler calls.

| Feature | Module | Gemini endpoint |
|---|---|---|
| Gork mention reply | `mention_responder` | interactions / 2.5-flash |
| `@gork is this real` fact-check | `ai_truth_check` | interactions / 2.5-flash |
| Per-user memory (cron + `@gork memory`) | `user_memory` | interactions / 2.5-flash |
| `good bot` persona reply | `good_bot_catgirl` | generateContent / 2.5-flash-lite (to migrate) |
| `@gork open issue` → GitHub | `github_issue` | generateContent / 2.5-flash-lite (to migrate) |
| `bad bot` reprocess | `reprocess_bad_bot` | none (calls `media` with the `telegram` profile) |

## Gork contract

- Every Gemini call includes the `googleSearch` tool. Replies do not list sources or citations.
- Context comes from the SQLite store: the last 10 minutes of the current chat, plus memory profiles of
  that chat's users.
- **Memories are isolated per chat.** A profile is keyed by `(chat_id, user_id)` and is built only from
  that user's own messages in that chat. Facts about other people or group events are never attributed
  to the user.
- **The persona resists prompt injection.** Gork stays in character, mocks attempts to override it, and
  never reveals its prompt.
- Without `GEMINI_API_KEY`, AI features reply with a "not configured" message and do not fail. The
  same applies to GitHub issues without `GITHUB_TOKEN` and `GITHUB_REPO`.

## Boundary

- Features talk to Telegram through the `update` and `context` they receive. They reach the store only
  through `utils.database`.
- Persona prompts live with their feature module, as the exception to "all strings in `config/strings.py`".
- `bad bot` finds the URL in the replied-to message, or in that message's parent when the reply targets
  the bot's own video.

## Known limitations

- Gemini request building, response parsing, and error handling are copied in each module. There is no
  shared client.
- `good bot` hardcodes `McClintock96` as the "alpha", and the router hardcodes `@guys_being_dudes_bot`.
