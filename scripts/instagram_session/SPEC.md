---
id: instagram-session
type: module-design
status: draft
title: Host-side Instagram session refresh
parent: architecture
---

## Responsibility

These scripts keep the bot's Instagram login alive without logging in from inside the container.
`refresh_session.py` is a standalone `uv run` script with its own inline dependencies (rookiepy,
requests). It does three things:

- Reads instagram.com cookies from the host browser. The default is Chrome, which needs an elevated run
  on Windows because of app-bound encryption.
- Writes them atomically as a Netscape `secrets/instagram_cookies.txt`, sends a keep-alive request,
  and saves any cookies Instagram rotates.
- Reports session health. It can send a Telegram alert when the session is dead.

`register_task.ps1` schedules the refresh every 6 hours with the highest privileges.

## Boundary

- The scripts run on the host only and never import `app/`. The only contract with the bot is the
  cookie file format and its location.
- `./secrets` is mounted read-only as a whole **directory**, not as a single file. That way the
  script's atomic replace is visible inside the running container without a restart.
- The bot reads the file through `INSTAGRAM_COOKIE_FILE`, as described in `media`.
