from urllib.parse import parse_qs, urlparse

import pytest

from src.core.auth.microsoft.microsoft_oauth import MicrosoftOAuth


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
