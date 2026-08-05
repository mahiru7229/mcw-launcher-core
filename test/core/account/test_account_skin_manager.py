from __future__ import annotations

from pathlib import Path

import pytest

from src.core.account.account_skin_manager import AccountSkinManager
from src.core.fs.paths import Paths
from src.models.account.account import Account
from src.models.account.account_source import AccountSource


PNG = b"\x89PNG\r\n\x1a\n" + b"skin-data"


class FakeResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, _size: int):
        yield from self._chunks


def test_cache_texture_writes_verified_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    monkeypatch.setattr("src.core.account.account_skin_manager.httpx.stream", lambda *args, **kwargs: FakeResponse([PNG]))

    path = AccountSkinManager.cache_texture("12345678-1234-1234-1234-1234567890ab", "https://textures.minecraft.net/texture/example")

    assert path == tmp_path / "accounts" / "skins" / "123456781234123412341234567890ab.png"
    assert path.read_bytes() == PNG


def test_cached_texture_uses_account_uuid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    account = Account("id", AccountSource.MICROSOFT, "Player", "123456781234123412341234567890ab")
    path = AccountSkinManager.texture_path(account.uuid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)

    assert AccountSkinManager.cached_texture(account) == path


def test_cache_texture_rejects_non_https(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")

    with pytest.raises(ValueError, match="HTTPS"):
        AccountSkinManager.cache_texture("123456781234123412341234567890ab", "http://example.invalid/skin.png")


def test_repository_persists_skin_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.core.account.database.account_database import AccountDatabase
    from src.core.account.repository.account_repository import AccountRepository
    from src.core.security.token_cipher import TokenCipher

    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(TokenCipher, "encrypt", staticmethod(lambda value, _purpose: value))
    monkeypatch.setattr(TokenCipher, "decrypt", staticmethod(lambda value, _purpose: value))
    AccountDatabase.initialize()
    account = Account(
        "skin-account",
        AccountSource.MICROSOFT,
        "PremiumPlayer",
        "123456781234123412341234567890ab",
        skin_url="https://textures.minecraft.net/texture/example",
        skin_variant="slim",
    )

    AccountRepository.save(account)
    loaded = AccountRepository.get(account.account_id)

    assert loaded is not None
    assert loaded.skin_url == account.skin_url
    assert loaded.skin_variant == "slim"
