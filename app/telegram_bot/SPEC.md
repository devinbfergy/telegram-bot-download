---
id: telegram-bot
type: module-design
status: draft
title: Telegram bot layer (routing & handlers)
parent: architecture
depends-on: [media, features, utils]
---

## Responsibility

This module adapts Telegram to the bot's capabilities. `app_factory` builds the `Application`, attaches
`AppSettings` as `application.settings["app_settings"]`, and initializes the SQLite schema. `router`
registers handlers and jobs. `handlers` unpack each update and delegate to `features` or `media`.
`StatusMessenger` owns the one status message per request and keeps it in the right forum thread.
It deletes transient progress after success and retains a terminal error after failure. If an edit
fails, ownership is preserved until a replacement is visible or the original can be cleaned up.

## Routing contract

python-telegram-bot runs every handler group, and the first match wins within a group. Routing depends
on that order:

- **Group −1:** the allowlist guard (`is_chat_allowed`). It raises `ApplicationHandlerStop` for
  updates from disallowed chats.
- **Group 0, most specific first:** `/start`, `bad bot` reply, `good bot`, `@gork is this real` reply,
  `@gork open (an) issue`, messages *from* `@guys_being_dudes_bot`, `@gork|@guys_being_dudes_bot memory`,
  generic `@gork|@guys_being_dudes_bot` mention, and finally the catch-all URL downloader
  (`TEXT & ~COMMAND`).
- **Group 2:** a passive logger. It stores every text or caption message in the SQLite store and never
  stops propagation.
- **JobQueue:** `user_memory_cron_job` runs every `user_memory_interval_hours`, starting 60 s after
  boot, unless the feature is disabled.

A new trigger must go above the catch-all. If it doesn't, the URL downloader also processes the message.

## Boundary

- Handlers hold no business logic. They extract inputs, build `StatusMessenger` and `Downloader`, and
  call into `features` or `media`.
- The catch-all downloads only URLs that look like media (detectors, or snapchat, facebook, instagram,
  or tiktok hosts). Other URLs are ignored without a reply.
- `StatusMessenger` is the one piece of this layer that `media` imports (see `architecture`).
