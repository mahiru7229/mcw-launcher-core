from __future__ import annotations

from time import time

import pytest

from src.core.auth.account_authentication import AccountAuthentication
from src.models.account.account import Account
from src.models.account.account_source import AccountSource


def _account(account_type: AccountSource, **overrides) -> Account:
    values = {
        "account_id": "account-id",
        "account_type": account_type,
        "username": "PremiumPlayer",
        "uuid": "12345678-1234-1234-1234-1234567890ab",
        "access_token": "minecraft-access-token",
        "refresh_token": "microsoft-refresh-token",
        "token_expires_at": int(time()) + 3600,
    }
    values.update(overrides)
    return Account(**values)


def test_offline_account_uses_offline_authentication() -> None:
    authentication = AccountAuthentication.authenticate(_account(AccountSource.OFFLINE))

    assert authentication.access_token == "0"
    assert authentication.user_type == "legacy"


def test_offline_account_never_touches_microsoft_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("Microsoft authentication must not run for an offline account")

    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAuthenticationGate.require_enabled", fail)
    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAccountAuthenticator.refresh", fail)

    authentication = AccountAuthentication.authenticate(_account(AccountSource.OFFLINE))

    assert authentication.player_name == "PremiumPlayer"
    assert authentication.access_token == "0"
    assert authentication.user_type == "legacy"


def test_microsoft_account_uses_minecraft_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAuthenticationGate.require_enabled", lambda: None)
    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAuthConfig.CLIENT_ID", "launcher-client-id")

    authentication = AccountAuthentication.authenticate(_account(AccountSource.MICROSOFT))

    assert authentication.player_name == "PremiumPlayer"
    assert authentication.uuid == "123456781234123412341234567890ab"
    assert authentication.access_token == "minecraft-access-token"
    assert authentication.client_id == "launcher-client-id"
    assert authentication.user_type == "msa"


def test_microsoft_account_refreshes_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account(AccountSource.MICROSOFT, token_expires_at=int(time()) - 1)
    refreshed = _account(AccountSource.MICROSOFT, access_token="fresh-token", token_expires_at=int(time()) + 3600)
    saved = []

    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAuthenticationGate.require_enabled", lambda: None)
    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAccountAuthenticator.refresh", lambda value: refreshed)
    monkeypatch.setattr(AccountAuthentication, "_save_account", saved.append)

    authentication = AccountAuthentication.authenticate(account)

    assert authentication.access_token == "fresh-token"
    assert saved == [refreshed]


def test_microsoft_account_requires_valid_profile_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.core.auth.account_authentication.MicrosoftAuthenticationGate.require_enabled", lambda: None)

    with pytest.raises(RuntimeError, match="profile UUID"):
        AccountAuthentication.authenticate(_account(AccountSource.MICROSOFT, uuid="invalid"))
