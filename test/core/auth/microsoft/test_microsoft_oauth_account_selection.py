from urllib.parse import parse_qs, urlparse

import pytest

from src.core.auth.microsoft.microsoft_oauth import MicrosoftOAuth
from src.models.auth.microsoft.oauth_session import OAuthSession


def test_create_session_requests_account_picker() -> None:
    session = MicrosoftOAuth.create_session()
    parameters = parse_qs(urlparse(session.authorization_url).query)

    assert parameters["prompt"] == ["select_account"]


def test_create_session_accepts_explicit_login_prompt() -> None:
    session = MicrosoftOAuth.create_session(prompt="login")
    parameters = parse_qs(urlparse(session.authorization_url).query)

    assert parameters["prompt"] == ["login"]


def test_create_session_rejects_unknown_prompt() -> None:
    with pytest.raises(ValueError, match="Unsupported Microsoft OAuth prompt"):
        MicrosoftOAuth.create_session(prompt="remember_latest_account")


def test_open_browser_uses_xdg_open_fallback_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    session = OAuthSession("https://login.example/authorize?secret=no", "verifier", "state")
    profile = type("Profile", (), {"os_name": "linux"})()

    monkeypatch.setattr("src.core.auth.microsoft.microsoft_oauth.webbrowser.open", lambda _url: False)
    monkeypatch.setattr("src.core.auth.microsoft.microsoft_oauth.PlatformInfo.current", lambda: profile)
    monkeypatch.setattr("src.core.auth.microsoft.microsoft_oauth.shutil.which", lambda name: "/usr/bin/xdg-open" if name == "xdg-open" else None)
    monkeypatch.setattr(
        "src.core.auth.microsoft.microsoft_oauth.subprocess.Popen",
        lambda command, **kwargs: calls.append((command, kwargs)) or object(),
    )

    assert MicrosoftOAuth.open_browser(session) is True
    assert calls[0][0] == ["/usr/bin/xdg-open", session.authorization_url]
    assert calls[0][1]["start_new_session"] is True


def test_open_browser_does_not_use_xdg_open_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    session = OAuthSession("https://login.example/authorize", "verifier", "state")
    profile = type("Profile", (), {"os_name": "windows"})()
    monkeypatch.setattr("src.core.auth.microsoft.microsoft_oauth.webbrowser.open", lambda _url: False)
    monkeypatch.setattr("src.core.auth.microsoft.microsoft_oauth.PlatformInfo.current", lambda: profile)

    assert MicrosoftOAuth.open_browser(session) is False
