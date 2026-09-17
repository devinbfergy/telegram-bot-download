import importlib.util
from pathlib import Path

from app.config.settings import AppSettings
from app.media.gallery_dl import resolve_instagram_cookiefile


def _load_refresh_session():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "instagram_session"
        / "refresh_session.py"
    )
    spec = importlib.util.spec_from_file_location("ig_refresh_session", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_cookiefile_prefers_existing_file(tmp_path):
    cookie_path = tmp_path / "instagram_cookies.txt"
    cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    settings = AppSettings(
        instagram_cookie_file=str(cookie_path), instagram_sessionid="ignored"
    )
    assert resolve_instagram_cookiefile(settings, tmp_path) == str(cookie_path)


def test_resolve_cookiefile_synthesizes_from_sessionid(tmp_path):
    settings = AppSettings(
        instagram_cookie_file=str(tmp_path / "missing.txt"),
        instagram_sessionid="abc123",
    )
    result = resolve_instagram_cookiefile(settings, tmp_path)
    assert result is not None
    text = Path(result).read_text(encoding="utf-8")
    assert "sessionid" in text
    assert "abc123" in text


def test_resolve_cookiefile_returns_none_without_credentials(tmp_path):
    settings = AppSettings(instagram_cookie_file="", instagram_sessionid="")
    assert resolve_instagram_cookiefile(settings, tmp_path) is None


def test_cookies_to_netscape_uses_rookiepy_expires():
    refresh = _load_refresh_session()
    text = refresh.cookies_to_netscape(
        [
            {
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "expires": 1700000000,
                "name": "sessionid",
                "value": "tok",
                "http_only": True,
            }
        ]
    )
    assert text.startswith("# Netscape HTTP Cookie File")
    assert "#HttpOnly_.instagram.com" in text
    assert "sessionid\ttok" in text
    assert "1700000000" in text


def test_cookies_to_netscape_accepts_expiration_date():
    refresh = _load_refresh_session()
    text = refresh.cookies_to_netscape(
        [
            {
                "domain": "instagram.com",
                "path": "/",
                "secure": False,
                "expirationDate": 99,
                "name": "ds_user_id",
                "value": "1",
            }
        ]
    )
    assert "99\tds_user_id\t1" in text
