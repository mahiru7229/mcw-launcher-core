from __future__ import annotations

from uuid import uuid4

import pytest

from src.core.account.account_manager import AccountManager
from src.core.account.repository.account_repository import AccountRepository
from src.core.auth.microsoft.microsoft_account_authenticator import MicrosoftAccountAuthenticator
from src.models.account.account import Account
from src.models.account.account_source import AccountSource


def _microsoft_account(username: str, profile_uuid: str, access_token: str, refresh_token: str) -> Account:
    return Account(account_id=str(uuid4()), account_type=AccountSource.MICROSOFT, username=username, uuid=profile_uuid, access_token=access_token, refresh_token=refresh_token, token_expires_at=123456)


def test_create_microsoft_account_adds_a_different_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = [_microsoft_account("FirstPlayer", "11111111-1111-1111-1111-111111111111", "first-access", "first-refresh")]
    authenticated = _microsoft_account("SecondPlayer", "22222222222222222222222222222222", "second-access", "second-refresh")
    selected = {"account_id": ""}

    monkeypatch.setattr(MicrosoftAccountAuthenticator, "authenticate", lambda: authenticated)
    monkeypatch.setattr(AccountRepository, "list_accounts", lambda: list(stored))
    monkeypatch.setattr(AccountRepository, "save", lambda account: stored.append(account))
    monkeypatch.setattr(AccountRepository, "set_selected_account", lambda account_id: selected.__setitem__("account_id", account_id) or True)

    result = AccountManager.create_microsoft_account()

    assert result is authenticated
    assert len(stored) == 2
    assert selected["account_id"] == authenticated.account_id


def test_create_microsoft_account_refreshes_same_profile_without_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = _microsoft_account("OldName", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "old-access", "old-refresh")
    authenticated = _microsoft_account("NewName", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "new-access", "new-refresh")
    saved = []
    selected = {"account_id": ""}

    monkeypatch.setattr(MicrosoftAccountAuthenticator, "authenticate", lambda: authenticated)
    monkeypatch.setattr(AccountRepository, "list_accounts", lambda: [existing])
    monkeypatch.setattr(AccountRepository, "save", saved.append)
    monkeypatch.setattr(AccountRepository, "set_selected_account", lambda account_id: selected.__setitem__("account_id", account_id) or True)

    result = AccountManager.create_microsoft_account()

    assert result.account_id == existing.account_id
    assert result.username == "NewName"
    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert saved == [existing]
    assert selected["account_id"] == existing.account_id
