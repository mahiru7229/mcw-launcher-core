from __future__ import annotations

import base64
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

import pytest

from src.core.account.database.account_database import AccountDatabase
from src.core.account.repository.account_repository import AccountRepository
from src.core.fs.paths import Paths
from src.core.security.account_integrity import AccountIntegrityError
from src.core.security.account_security_manager import AccountSecurityManager
from src.core.security.token_cipher import TokenCipher
from src.models.account.account import Account
from src.models.account.account_source import AccountSource


@contextmanager
def _sqlite_session() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(Paths.account_database_path())
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class FakeDPAPI:
    CRYPTPROTECT_UI_FORBIDDEN = 1

    @staticmethod
    def CryptProtectData(data, description, entropy, reserved, prompt, flags):
        marker = base64.b64encode(entropy or b"")
        return marker + b"|" + bytes(data)

    @staticmethod
    def CryptUnprotectData(data, entropy, reserved, prompt, flags):
        marker, plaintext = bytes(data).split(b"|", 1)
        if marker != base64.b64encode(entropy or b""):
            raise ValueError("entropy mismatch")
        return "description", plaintext


def _prepare(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(TokenCipher, "_backend", FakeDPAPI)
    AccountDatabase.initialize()


def _account() -> Account:
    return Account(
        account_id="account-id",
        account_type=AccountSource.MICROSOFT,
        username="PremiumPlayer",
        uuid="123456781234123412341234567890ab",
        access_token="short-lived-access",
        refresh_token="long-lived-refresh",
        token_expires_at=123456,
    )


def test_microsoft_access_token_is_not_persisted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)

    AccountRepository.save(_account())

    with _sqlite_session() as connection:
        row = connection.execute("SELECT access_token, refresh_token, token_cipher_version, record_integrity FROM accounts").fetchone()
    assert row[0] is None
    assert str(row[1]).startswith(TokenCipher.PREFIX)
    assert row[2] == TokenCipher.VERSION
    assert row[3]

    loaded = AccountRepository.get("account-id")
    assert loaded is not None
    assert loaded.access_token is None
    assert loaded.refresh_token == "long-lived-refresh"


def test_integrity_tampering_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    AccountRepository.save(_account())

    with _sqlite_session() as connection:
        connection.execute("UPDATE accounts SET username = 'TamperedPlayer' WHERE account_id = 'account-id'")

    with pytest.raises(AccountIntegrityError, match="integrity"):
        AccountRepository.get("account-id")


def test_security_migration_reprotects_legacy_refresh_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    legacy_blob = FakeDPAPI.CryptProtectData(b"legacy-refresh", TokenCipher.LEGACY_DESCRIPTION, None, None, None, 0)
    legacy_value = base64.b64encode(legacy_blob).decode("ascii")

    with _sqlite_session() as connection:
        connection.execute(
            "INSERT INTO accounts (account_id, account_type, username, uuid, refresh_token, token_expires_at, token_cipher_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("legacy", "microsoft", "Legacy", "a" * 32, legacy_value, 123, 1),
        )

    report = AccountSecurityManager.migrate_if_needed()

    assert report.migrated_account_count == 1
    with _sqlite_session() as connection:
        row = connection.execute("SELECT refresh_token, token_cipher_version, record_integrity FROM accounts WHERE account_id = 'legacy'").fetchone()
    assert str(row[0]).startswith(TokenCipher.PREFIX)
    assert row[1] == TokenCipher.VERSION
    assert row[2]
