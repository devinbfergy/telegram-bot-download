# Telegram Video Download Bot

A Telegram bot that downloads videos from YouTube, Instagram, Facebook, and other supported sites using [yt-dlp](https://github.com/yt-dlp/yt-dlp) and sends them directly to your chat.

## Features

- Download videos from a wide range of platforms.
- Automatic detection of video links in messages.
- Sends videos directly to Telegram chats (subject to Telegram's 50MB upload limit).
- Built with [python-telegram-bot](https://python-telegram-bot.org/) and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed on your system.
- A Telegram Bot Token. You can get one from [@BotFather](https://t.me/BotFather).
- See the [official Telegram documentation on creating a bot](https://core.telegram.org/bots#3-how-do-i-create-a-bot) for step-by-step instructions.
- **Important:** To allow your bot to read all messages in a group, you must disable privacy mode for your bot via @BotFather. See [Telegram Privacy Mode](https://core.telegram.org/bots#privacy-mode) for details.

## Building the Docker Image

```sh
docker build -t telegram-video-download-bot .
```

## Running the Container

You **must** provide your Telegram Bot Token as an environment variable named `API_TOKEN`.

```sh
docker run -e API_TOKEN=your_telegram_bot_token_here telegram-video-download-bot
```

- Replace `your_telegram_bot_token_here` with your actual bot token from BotFather.
- The bot will start and listen for messages.

### Run with automatic restart

To ensure the bot always restarts if it crashes or the host reboots, use Docker's `--restart always` flag:

```sh
docker run --restart always -e API_TOKEN=your_telegram_bot_token_here telegram-video-download-bot
```

## Environment Variables

| Variable   | Description                    | Required |
|------------|--------------------------------|----------|
| API_TOKEN  | Telegram Bot API token         | Yes      |

## Usage

1. Start the bot using the instructions above.
2. Send a message containing a video link (YouTube, Instagram, Facebook, etc.) to your bot on Telegram.
3. The bot will reply with the downloaded video (if supported and under 50MB).

## Contribution Guidelines

We welcome contributions! To contribute:

1. Fork this repository.
2. Create a new branch for your feature or bugfix.
3. Make your changes and ensure code quality (formatting, linting).
4. Submit a pull request with a clear description of your changes.

### Code Style

- Use [ruff](https://github.com/astral-sh/ruff) for linting and formatting.
- Write clear, concise commit messages.
- Add or update documentation and comments as needed.

### Issues

- Please search existing issues before opening a new one.
- Provide detailed information and steps to reproduce any bugs.

## Code of Conduct

Please be respectful and considerate in your communications and contributions. See [Contributor Covenant](https://www.contributor-covenant.org/) for guidelines.

## License

This project is licensed under the MIT License.

## Disclaimer

This bot is intended for personal use. Please respect the terms of service of the platforms you download from and do not use this bot for copyright infringement or any illegal activities.