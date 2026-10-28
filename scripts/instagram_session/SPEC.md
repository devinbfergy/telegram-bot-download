---
id: instagram-session
type: module-design
status: draft
title: Host-side Instagram session keep-alive
parent: architecture
---

## Responsibility

These scripts keep the bot's Instagram login alive and make the bot look like the same Chrome on
this Windows PC, so Instagram does not flag the session as a new or hacked device.

`refresh_session.py` is a standalone `uv run` script (inline deps: requests, websocket-client).
Chrome 127+ uses app-bound cookie encryption, so cookies cannot be lifted from the everyday
profile (a copied cookie DB decrypts to nothing). Instead the bot owns a **dedicated Chrome
profile** at `%LOCALAPPDATA%\telegram-bot-download\chrome-profile`:

- `--login` (once): opens a visible Chrome on that profile and waits for a `sessionid`.
- default run (scheduled): starts the installed Chrome headless on the profile, loads
  instagram.com (a genuine browser visit, so Instagram rotates cookies normally), reads the
  cookies over the DevTools protocol, and writes them atomically as `secrets/instagram_cookies.txt`.
  It also records Chrome's real request headers (User-Agent, `sec-ch-ua*`, `accept-language`) in
  `secrets/instagram_session.json`.
- If the session is dead it logs it and can send a Telegram alert.

`register_task.ps1` schedules the refresh every 4 hours with up to 10 minutes of jitter. No
elevation is needed.

## Boundary

- The scripts run on the host only and never import `app/`. The contract with the bot is two
  files in `./secrets`: the Netscape cookie file and `instagram_session.json`.
- `./secrets` is mounted read-only as a whole **directory**, so the atomic replace is visible in the
  running container without a restart.
- The bot reads the cookies through `INSTAGRAM_COOKIE_FILE` and the headers from
  `instagram_session.json` beside it (`media` sends that User-Agent in yt-dlp and gallery-dl).
- Chrome is launched with the bot profile only; the user's everyday profile is never touched.
