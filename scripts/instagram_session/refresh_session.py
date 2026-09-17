# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "rookiepy>=0.5",
#     "requests>=2.32",
# ]
# ///
"""
Refresh the Instagram session used by the Telegram bot.

What it does:
  1. Extracts instagram.com cookies from the local Chrome profile
     (requires an elevated/admin run on Windows: Chrome >= 130 uses
     app-bound encryption).
  2. Writes them as a Netscape cookies.txt to secrets/instagram_cookies.txt
     (atomic replace; the directory is mounted read-only into the container).
  3. Performs a keep-alive request against Instagram so the session stays
     active, capturing any rotated cookies (Instagram periodically re-issues
     sessionid) and saving them back.
  4. Reports session health. Optionally sends a Telegram alert when the
     session is dead (needs API_TOKEN in .env and --notify-chat-id /
     IG_NOTIFY_CHAT_ID).

Usage:
    uv run scripts/instagram_session/refresh_session.py
    uv run scripts/instagram_session/refresh_session.py --browser firefox
    uv run scripts/instagram_session/refresh_session.py --notify-chat-id 123456
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import logging
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS_DIR = REPO_ROOT / "secrets"
COOKIE_FILE = SECRETS_DIR / "instagram_cookies.txt"
LOG_FILE = SECRETS_DIR / "refresh.log"
ENV_FILE = REPO_ROOT / ".env"

IG_APP_ID = "936619743392459"
IG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

logger = logging.getLogger("ig_session_refresh")


def _setup_logging() -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ):
        handler.setFormatter(fmt)
        logger.addHandler(handler)


def _is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _read_env_token() -> str:
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("API_TOKEN="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def cookie_expires(cookie: dict) -> int:
    raw = cookie.get("expires")
    if raw in (None, 0, "0"):
        raw = cookie.get("expirationDate")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def cookies_to_netscape(cookies: list[dict]) -> str:
    """Serialize rookiepy (or Chrome DevTools-style) cookies to Netscape format."""
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in cookies:
        name = cookie.get("name") or ""
        if not name:
            continue
        domain = cookie.get("domain") or ""
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.get("path") or "/"
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        value = cookie.get("value") or ""
        expires = cookie_expires(cookie)
        http_only = cookie.get("http_only") or cookie.get("httpOnly")
        if http_only:
            domain = f"#HttpOnly_{domain}"
        lines.append(
            f"{domain}\t{include_sub}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
        )
    return "\n".join(lines) + "\n"


def extract_cookies(browser: str) -> list[dict]:
    """Extract instagram.com cookies from the given browser via rookiepy."""
    import rookiepy

    loader = getattr(rookiepy, browser, None)
    if loader is None:
        raise ValueError(f"Unsupported browser: {browser}")
    cookies = loader(["instagram.com"])
    if not cookies:
        raise RuntimeError(
            f"No instagram.com cookies found in {browser}. "
            "Make sure you are logged into Instagram in that browser."
        )
    return cookies


def write_netscape(cookies: list[dict], dest: Path) -> None:
    """Atomically write cookies in Netscape cookies.txt format."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = cookies_to_netscape(cookies)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(dest.parent), prefix=".cookies_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp_name, dest)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def keep_alive(cookie_file: Path) -> tuple[bool, str]:
    """
    Hit Instagram with the stored cookies to keep the session active and
    capture rotated cookies. Returns (alive, detail).
    """
    from http.cookiejar import MozillaCookieJar

    import requests

    jar = MozillaCookieJar(str(cookie_file))
    jar.load(ignore_discard=True, ignore_expires=True)

    session = requests.Session()
    session.cookies = jar
    session.headers.update({"User-Agent": IG_UA, "x-ig-app-id": IG_APP_ID})

    ds_user_id = next((c.value for c in jar if c.name == "ds_user_id"), "")
    urls = []
    if ds_user_id:
        urls.append(f"https://www.instagram.com/api/v1/feed/user/{ds_user_id}/?count=1")
    urls.append("https://www.instagram.com/accounts/edit/")

    for url in urls:
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException as exc:
            return False, f"network error during keep-alive: {exc}"

        if resp.status_code == 200 and "accounts/login" not in resp.url:
            try:
                jar.save(ignore_discard=True, ignore_expires=False)
            except OSError as exc:
                logger.warning("Could not save rotated cookies: %s", exc)
            return True, f"keep-alive OK via {url}"

        if resp.status_code in (401, 403) or "accounts/login" in resp.url:
            return False, (
                f"session rejected by Instagram (HTTP {resp.status_code} via {url})"
            )

    return False, "unexpected keep-alive response"


def notify_telegram(text: str, chat_id: str, token: str) -> None:
    import requests

    if not chat_id or not token:
        logger.info(
            "Telegram alert skipped (no chat id or bot token). Message: %s", text
        )
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        if resp.status_code == 200:
            logger.info("Telegram alert sent.")
        else:
            logger.warning("Telegram alert failed: HTTP %s", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Telegram alert failed: %s", exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser",
        default="chrome",
        help="Browser to extract cookies from (default: chrome)",
    )
    parser.add_argument(
        "--notify-chat-id",
        default=os.getenv("IG_NOTIFY_CHAT_ID", ""),
        help="Telegram chat id to alert when the session is dead",
    )
    parser.add_argument(
        "--skip-keepalive",
        action="store_true",
        help="Only extract and write cookies",
    )
    args = parser.parse_args()

    _setup_logging()
    logger.info(
        "=== Instagram session refresh started (%s) ===",
        datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    )

    if os.name == "nt" and args.browser == "chrome" and not _is_admin():
        logger.error(
            "Not running as admin. Chrome >= 130 uses app-bound encryption, so "
            "cookie extraction requires elevation. Re-run from an elevated shell "
            "or register the scheduled task with 'Run with highest privileges'."
        )
        return 2

    try:
        cookies = extract_cookies(args.browser)
    except Exception as exc:  # noqa: BLE001
        logger.error("Cookie extraction failed: %s", exc)
        notify_telegram(
            f"⚠️ Instagram session refresh: extraction failed ({exc}). "
            "The bot may fail to download Instagram media.",
            args.notify_chat_id,
            _read_env_token(),
        )
        return 1

    names = sorted({c.get("name", "") for c in cookies})
    logger.info(
        "Extracted %d cookies from %s: %s", len(cookies), args.browser, ", ".join(names)
    )

    if "sessionid" not in names:
        logger.error(
            "No 'sessionid' cookie found - Instagram login is missing or expired "
            "in the browser."
        )
        notify_telegram(
            "⚠️ Instagram session refresh: no sessionid cookie in Chrome. "
            "Log into instagram.com in Chrome, then the task will recover automatically.",
            args.notify_chat_id,
            _read_env_token(),
        )
        return 1

    write_netscape(cookies, COOKIE_FILE)
    logger.info("Wrote %s", COOKIE_FILE)

    if args.skip_keepalive:
        return 0

    alive, detail = keep_alive(COOKIE_FILE)
    if alive:
        logger.info("Session alive: %s", detail)
        return 0

    logger.error("Session DEAD: %s", detail)
    notify_telegram(
        "❌ Instagram session is dead (Instagram rejected the stored cookies). "
        "Log into instagram.com in Chrome; the scheduled refresh task will pick it up. "
        f"Detail: {detail}",
        args.notify_chat_id,
        _read_env_token(),
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
