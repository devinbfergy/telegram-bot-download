# Telegram Video Download Bot

A Telegram group bot that downloads media from YouTube, Instagram, Facebook, and other platforms, and also has an AI assistant ("Gork") powered by Google Gemini with live web-search grounding.

## Features

- Download videos/images from a wide range of platforms via yt-dlp and gallery-dl.
- Automatic detection of video/image links in messages.
- Sends media directly to Telegram chats (subject to Telegram's 50MB upload limit).
- Reply to a video with `bad bot` to re-process it for better Telegram compatibility.
- **Gork AI assistant** — mention `@gork` (or the bot's username) in any message for a Gemini-powered reply with full web search grounding and recent chat history as context.
- **Fact-check** — reply to any message with `@gork is this real` for a sourced verdict.
- **GitHub issue creation** — `@gork open issue <title>` summarises the chat and files a GitHub issue.
- **User memory** — a daily job condenses each person's messages into a per-chat profile that Gork uses for personal replies; `@gork memory` shows them.
- **Chat allowlist** — only allowlisted chats and admin DMs are served; everything else is ignored.
- All Gemini responses are grounded with Google Search, so answers reflect current events.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/) installed.
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather).
- **Important:** Disable privacy mode for your bot via @BotFather so it can read all group messages. See [Telegram Privacy Mode](https://core.telegram.org/bots#privacy-mode).
- A [Google Gemini API key](https://aistudio.google.com/app/apikey) for AI features.

---

## Secrets & Environment Variables

All secrets live in a `.env` file in the project root. **This file is gitignored — never commit it.**

Create it once:

```
API_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key

# Optional
GITHUB_TOKEN=your_github_pat          # for @gork open issue
GITHUB_REPO=owner/repo                # for @gork open issue
INSTAGRAM_SESSIONID=your_sessionid   # optional fallback if cookies.txt is missing
LOG_LEVEL=INFO                        # DEBUG | INFO | WARNING | ERROR
LOG_JSON=0                            # 1 = structured JSON logs
```

`docker-compose.yml` reads these automatically via `${VAR}` substitution. You never pass secrets on the command line.

### Variable reference

| Variable            | Description                                              | Required |
|---------------------|----------------------------------------------------------|----------|
| `API_TOKEN`         | Telegram Bot API token from @BotFather                   | Yes      |
| `GEMINI_API_KEY`    | Google Gemini API key — powers all Gork AI features      | Yes (for AI) |
| `GITHUB_TOKEN`      | GitHub personal access token for issue creation          | No       |
| `GITHUB_REPO`       | `owner/repo` slug for issue creation                     | No       |
| `INSTAGRAM_SESSIONID` | Instagram session cookie (fallback if cookies.txt is missing) | No |
| `INSTAGRAM_COOKIE_FILE` | Path to Netscape cookies.txt (set automatically in compose) | No |
| `LOG_LEVEL`         | Logging verbosity (default: `INFO`)                      | No       |
| `LOG_JSON`          | Set to `1` for structured JSON logs (default: `0`)       | No       |
| `ALLOWED_CHAT_IDS`  | Comma-separated chat IDs the bot serves (empty = all)    | No       |
| `ADMIN_USERNAMES` / `ADMIN_USER_IDS` | Admins whose DMs are allowed            | No       |
| `SQLITE_DB_PATH`    | SQLite file (default: `/data/bot_messages.db`)           | No       |
| `USER_MEMORY_ENABLED` | `0` disables the memory job (default: `1`)             | No       |
| `USER_MEMORY_INTERVAL_HOURS` / `USER_MEMORY_WINDOW_HOURS` | Memory job interval / message window (default: 24) | No |

### Instagram session cookies

Instagram blocks unauthenticated downloads. Keep a live session on the host and mount it into the container:

1. Log into [instagram.com](https://www.instagram.com) in Chrome.
2. From an **elevated** PowerShell (Chrome ≥ 130 uses app-bound cookie encryption):

```powershell
uv run scripts/instagram_session/refresh_session.py
```

This writes `secrets/instagram_cookies.txt` (gitignored). `docker-compose.yml` bind-mounts `./secrets` into the container at `/data/secrets`.

3. Register a scheduled refresh (every 6 hours, highest privileges):

```powershell
.\scripts\instagram_session\register_task.ps1
```

Optional fallback: set `INSTAGRAM_SESSIONID` in `.env`. The cookie file takes precedence when present.

---

## Deploying / Running

The bot is managed entirely through `docker compose`. All commands are run from the project root.

### First-time setup

```sh
# 1. Create your .env file (see above)

# 2. Build the image and start the container
docker compose up --build -d
```

The container starts with `restart: always`, so it comes back automatically after crashes or host reboots.

### Updating the bot (after code changes)

```sh
docker compose up --build -d
```

This rebuilds the image from the current source and replaces the running container with zero downtime. Your SQLite message history is preserved in the named Docker volume.

### View logs

```sh
docker compose logs -f
```

### Stop the bot

```sh
docker compose down
```

### Stop and wipe all state (including the SQLite database)

```sh
docker compose down -v
```

---

## Data Persistence

The bot stores chat messages in a SQLite database (pruned after 7 days) to give Gork conversation context and to build per-user memory profiles. The database lives in a named Docker volume (`bot_data`) mounted at `/data/bot_messages.db` inside the container.

- The volume **survives** `docker compose up --build -d` (normal deploys).
- The volume is **deleted** only by `docker compose down -v` (explicit wipe).
- Instagram cookies live on the host at `secrets/instagram_cookies.txt` (bind-mounted read-only).

---

## Development

### Install dependencies

```sh
uv sync
```

### Run locally (without Docker)

```sh
export API_TOKEN=your_token
export GEMINI_API_KEY=your_key
uv run main.py
```

### Run tests

```sh
uv run pytest -v
```

### Lint & format

```sh
uv run ruff check .
uv run ruff format .
```

---

## Architecture overview

```
app/
├── config/          # Settings (AppSettings dataclass) & user-facing strings
├── core/            # Exceptions, logging, shared types
├── features/        # AI truth-check, Gork mention responder, GitHub issues, catgirl
├── media/           # Download → inspect → post-process → send pipeline
├── telegram_bot/    # Handlers, router, app factory, status messenger
├── utils/           # Concurrency helpers, filesystem, SQLite database, validation
└── tests/           # pytest test suite
```

All Gemini calls go through raw `aiohttp` REST requests. The target endpoint is
`/v1beta/interactions` with `gemini-2.5-flash` (mentions, fact-check, user memory); `good bot` and
GitHub-issue still use the older `models/gemini-2.5-flash-lite:generateContent` and are being migrated.
Every call includes the `googleSearch` tool so responses are grounded with live web results.

Design intent, boundaries and decisions live in the spec graph: `goal-and-requirements.md`,
`architecture.md`, and a `SPEC.md` beside each module.

---

## Contribution Guidelines

1. Fork the repository and create a feature branch.
2. Run `uv run ruff check .` and `uv run pytest -v` before submitting.
3. Submit a pull request with a clear description of the change.
4. Never commit `.env` or any file containing secrets.

---

## License

MIT License.

## Disclaimer

This bot is intended for personal use. Respect the terms of service of the platforms you download from and do not use this bot for copyright infringement or any illegal activities.
