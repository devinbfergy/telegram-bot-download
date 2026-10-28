---
id: goal
type: goal-and-requirements
status: draft
title: Telegram media-download bot with Gork AI assistant
---

## Goal

Keep a private group chat of friends in Telegram. When someone drops a link to a video, reel, short, or
photo post, the bot sends the media straight into the chat, so nobody has to leave Telegram. The same bot
is also "Gork", a sarcastic Gemini-powered member of the group. Gork answers questions, fact-checks
claims, and remembers who people are.

## Problem

Links to TikTok, Instagram, YouTube, Facebook, X, and Reddit force everyone to open another app, often
behind a login wall. Inline Telegram previews are unreliable or missing. The group also wants an AI it
can ask in place, one that knows current events and the chat's own context.

## Audience

A small number of private friend-group chats run by the owner (the admin). Only allowlisted chats and
the admin's direct messages are served. Every other update is dropped.

## Capabilities

- **Link → media.** The bot detects media links in any message, downloads the media (yt-dlp, with
  gallery-dl as fallback), and replies with the video, a photo album, or a slideshow video built from
  images. A short caption is taken from the source post. Telegram's 50 MB upload limit applies.
- **Self-repair.** Downloads that come out frozen are retried with a fallback profile and then with
  gallery-dl. Replying `bad bot` to a post re-downloads it with a Telegram-optimized profile.
- **Instagram access.** Instagram is downloaded with a logged-in session. A host-side script keeps that
  session's cookies fresh.
- **Gork chat.** Mentioning `@gork` or the bot's handle gets an in-character reply. Each reply is
  grounded in Google Search and in the last 10 minutes of chat.
- **Fact-check.** Replying `@gork is this real` to a message returns a sourced verdict.
- **User memory.** A periodic job condenses each person's recent messages into a short profile per
  chat. Gork uses these profiles to personalize replies, and `@gork memory` shows them.
- **GitHub issues.** `@gork open issue …` summarizes recent chat and files an issue on the configured repo.
- **Good bot.** Saying `good bot` gets a playful, persona-driven reply.

## Non-goals

- Public or multi-tenant use. The bot serves only allowlisted chats and is not meant for strangers or
  arbitrary groups.

## Principles

- Media failures are handled quietly. The bot works through its fallback chain before it reports an
  error. Transient progress is cleaned up after success; a terminal failure remains visible.
- Secrets come only from the environment or mounted files and are never committed.
- Deployment is a single Docker Compose service. Chat history and memories persist across rebuilds.
