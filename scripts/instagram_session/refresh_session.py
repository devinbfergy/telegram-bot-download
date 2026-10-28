# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests>=2.32",
#     "websocket-client>=1.8",
# ]
# ///
"""
Keep the Instagram session used by the Telegram bot alive, as a real Chrome would.

Why a dedicated Chrome profile: Chrome (>= 127) encrypts cookies with app-bound
encryption, so they cannot be copied out of your everyday profile. Instead the bot owns a
persistent Chrome profile (outside the repo). You log in to Instagram in it ONCE
(`--login`), and from then on this script:

  1. starts the installed Chrome headless on that profile (same TLS fingerprint, same
     User-Agent and client hints as your browser, same machine and IP),
  2. loads instagram.com so the session is genuinely used and Instagram rotates cookies,
  3. reads the cookies over the DevTools protocol and writes them atomically as a Netscape
     secrets/instagram_cookies.txt (mounted read-only into the container),
  4. records Chrome's real request headers in secrets/instagram_session.json so the bot's
     yt-dlp / gallery-dl send the very same User-Agent,
  5. reports session health, optionally alerting via Telegram when the login is dead.

Usage:
    uv run scripts/instagram_session/refresh_session.py --login   # once: log in, visible
    uv run scripts/instagram_session/refresh_session.py           # refresh (scheduled)
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import http.server
import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS_DIR = REPO_ROOT / "secrets"
COOKIE_FILE = SECRETS_DIR / "instagram_cookies.txt"
FINGERPRINT_FILE = SECRETS_DIR / "instagram_session.json"
LOG_FILE = SECRETS_DIR / "refresh.log"
ENV_FILE = REPO_ROOT / ".env"
PROFILE_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "telegram-bot-download"
    / "chrome-profile"
)

IG_HOME = "https://www.instagram.com/"
IG_LOGIN = "https://www.instagram.com/accounts/login/"
FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

logger = logging.getLogger("ig_session_refresh")


# --------------------------------------------------------------------------- logging
def _setup_logging() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ):
        handler.setFormatter(fmt)
        logger.addHandler(handler)


def _read_env_token() -> str:
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("API_TOKEN="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


# --------------------------------------------------------------------------- cookies
def cookie_expires(cookie: dict) -> int:
    raw = cookie.get("expires")
    if raw in (None, 0, "0"):
        raw = cookie.get("expirationDate")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def cookies_to_netscape(cookies: list[dict]) -> str:
    """Serialize cookies (rookiepy- or DevTools-style dicts) to Netscape format."""
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


def _normalize_ig_cookies(raw: list[dict]) -> list[dict]:
    return [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "http_only": c.get("httpOnly", False),
            "expires": int(c["expires"]) if c.get("expires", -1) > 0 else 0,
        }
        for c in raw
        if "instagram.com" in c.get("domain", "")
    ]


# --------------------------------------------------------------------------- chrome
def find_chrome() -> str | None:
    candidates = [
        os.path.join(
            os.environ.get(var, ""), "Google", "Chrome", "Application", "chrome.exe"
        )
        for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
    ]
    return next((c for c in candidates if os.path.isfile(c)), None)


class ChromeSession:
    """A Chrome instance on the bot profile, driven over the DevTools protocol."""

    def __init__(self, headless: bool = True) -> None:
        chrome = find_chrome()
        if not chrome:
            raise RuntimeError("chrome.exe not found")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        (PROFILE_DIR / "DevToolsActivePort").unlink(missing_ok=True)
        args = [
            chrome,
            "--remote-debugging-port=0",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
        ]
        if headless:
            args += ["--headless=new", "--disable-gpu"]
        args.append("about:blank")
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        port_file = PROFILE_DIR / "DevToolsActivePort"
        deadline = time.time() + 45
        while time.time() < deadline and not port_file.is_file():
            time.sleep(0.3)
        if not port_file.is_file():
            self.close()
            raise RuntimeError(
                "Chrome did not start (is another Chrome using the bot profile?)"
            )
        self.port = port_file.read_text().splitlines()[0].strip()
        import websocket

        info = json.loads(
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/version", timeout=10
            ).read()
        )
        self.user_agent: str = info.get("User-Agent", FALLBACK_UA)
        self._ws = websocket.create_connection(info["webSocketDebuggerUrl"], timeout=60)
        self._next_id = 0

    def call(self, method: str, params: dict | None = None, session: str = "") -> dict:
        self._next_id += 1
        msg: dict = {"id": self._next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self._ws.send(json.dumps(msg))
        while True:
            reply = json.loads(self._ws.recv())
            if reply.get("id") == self._next_id:
                break
        if "error" in reply:
            raise RuntimeError(f"DevTools {method}: {reply['error']}")
        return reply["result"]

    def cookies(self) -> list[dict]:
        return self.call("Storage.getCookies")["cookies"]

    def open_page(self, url: str) -> str:
        """Open a tab (with a non-headless User-Agent) and return its session id."""
        target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = self.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )["sessionId"]
        self.call(
            "Network.setUserAgentOverride",
            {"userAgent": real_user_agent(self.user_agent)},
            session,
        )
        self.call("Page.navigate", {"url": url}, session)
        return session

    def page_url(self, session: str) -> str:
        res = self.call("Runtime.evaluate", {"expression": "location.href"}, session)
        return str(res.get("result", {}).get("value", ""))

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.call("Browser.close")  # graceful: flushes cookies to disk
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        _kill_profile_chrome()


def real_user_agent(ua: str) -> str:
    return ua.replace("HeadlessChrome", "Chrome")


def _kill_profile_chrome() -> None:
    """Make sure no chrome.exe is left holding the bot profile."""
    marker = str(PROFILE_DIR).replace("'", "''")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like '*{marker}*' }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
                "-ErrorAction SilentlyContinue }"
            ),
        ],
        capture_output=True,
        check=False,
    )


# --------------------------------------------------------------------------- fingerprint
def capture_headers(browser: ChromeSession) -> dict[str, str]:
    """Record the request headers this Chrome really sends (UA, sec-ch-ua*, ...)."""
    captured: dict[str, str] = {}
    got = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/probe") and not got.is_set():
                captured.update({k.lower(): v for k, v in self.headers.items()})
                got.set()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>ok</body></html>")

        def log_message(self, *_args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        browser.call(
            "Target.createTarget",
            {"url": f"http://localhost:{server.server_address[1]}/probe"},
        )
        got.wait(timeout=30)
    finally:
        server.shutdown()
    if not captured:
        raise RuntimeError("Chrome did not make a probe request")
    keep = (
        "user-agent",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "accept-language",
    )
    fp = {k: v for k, v in captured.items() if k in keep}
    if "sec-ch-ua" in fp:
        fp["sec-ch-ua"] = fp["sec-ch-ua"].replace("HeadlessChrome", "Google Chrome")
    fp["user-agent"] = real_user_agent(fp.get("user-agent", browser.user_agent))
    return fp


def save_fingerprint(fp: dict[str, str]) -> None:
    tmp = FINGERPRINT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(fp, indent=2), encoding="utf-8")
    os.replace(tmp, FINGERPRINT_FILE)


# --------------------------------------------------------------------------- notify
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


# --------------------------------------------------------------------------- commands
def do_login() -> int:
    """Open a visible Chrome on the bot profile and wait until Instagram is logged in."""
    logger.info(
        "Opening Chrome on the bot profile. Log in to Instagram in that window."
    )
    browser = ChromeSession(headless=False)
    try:
        browser.call("Target.createTarget", {"url": IG_LOGIN})
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            time.sleep(3)
            try:
                names = {c["name"] for c in _normalize_ig_cookies(browser.cookies())}
            except Exception:  # noqa: BLE001 - window closed by the user
                break
            if "sessionid" in names:
                time.sleep(5)  # let Instagram finish setting cookies
                logger.info("Login detected. The bot profile now holds a session.")
                return 0
        logger.error("No Instagram login detected (timed out or window closed).")
        return 1
    finally:
        browser.close()


def do_refresh(args: argparse.Namespace) -> int:
    if not (PROFILE_DIR / "Default").exists():
        logger.error(
            "Bot Chrome profile has no login yet. Run once: "
            "uv run scripts/instagram_session/refresh_session.py --login"
        )
        return 1
    try:
        browser = ChromeSession(headless=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not start Chrome: %s", exc)
        return 1

    try:
        session = browser.open_page(IG_HOME)
        time.sleep(random.uniform(6, 10))  # let the page settle like a person would
        final_url = browser.page_url(session)
        cookies = _normalize_ig_cookies(browser.cookies())
        names = {c["name"] for c in cookies}
        try:
            save_fingerprint(capture_headers(browser))
            logger.info(
                "Captured Chrome headers: %s", real_user_agent(browser.user_agent)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Header capture failed: %s", exc)
    finally:
        browser.close()

    token = _read_env_token()
    if "sessionid" not in names or "accounts/login" in final_url:
        logger.error(
            "Session DEAD: no valid Instagram login in the bot profile (url=%s).",
            final_url,
        )
        notify_telegram(
            "❌ Instagram session is dead. Re-login once with: "
            "uv run scripts/instagram_session/refresh_session.py --login",
            args.notify_chat_id,
            token,
        )
        return 1

    write_netscape(cookies, COOKIE_FILE)
    logger.info("Session alive. Wrote %d cookies to %s", len(cookies), COOKIE_FILE)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--login", action="store_true", help="One-time interactive Instagram login"
    )
    parser.add_argument(
        "--notify-chat-id",
        default=os.getenv("IG_NOTIFY_CHAT_ID", ""),
        help="Telegram chat id to alert when the session is dead",
    )
    args = parser.parse_args()

    _setup_logging()
    logger.info(
        "=== Instagram session %s started (%s) ===",
        "login" if args.login else "refresh",
        datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    )
    return do_login() if args.login else do_refresh(args)


if __name__ == "__main__":
    sys.exit(main())
