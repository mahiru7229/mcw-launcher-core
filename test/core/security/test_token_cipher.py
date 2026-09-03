from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet

from src.core.security.token_cipher import TokenCipher
from src.core.fs.paths import Paths


class FakeDPAPI:
    CRYPTPROTECT_UI_FORBIDDEN = 1

    @staticmethod
    def CryptProtectData(data, description, entropy, reserved, prompt, flags):
        marker = base64.b64encode(entropy or b"").decode("ascii").encode("ascii")
        return marker + b"|" + bytes(data)

    @staticmethod
    def CryptUnprotectData(data, entropy, reserved, prompt, flags):
        marker, plaintext = bytes(data).split(b"|", 1)
        expected = base64.b64encode(entropy or b"").decode("ascii").encode("ascii")
        if marker != expected:
            raise ValueError("entropy mismatch")
        return "description", plaintext


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.values[(service, username)] = value


class UnavailableKeyring:
    @staticmethod
    def get_password(_service: str, _username: str) -> str | None:
        raise RuntimeError("Secret Service unavailable")


def test_v2_cipher_uses_context_and_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TokenCipher, "_backend", FakeDPAPI)

    protected = TokenCipher.encrypt("refresh-secret", "account:one:refresh")

    assert protected.startswith(TokenCipher.PREFIX)
    assert TokenCipher.decrypt(protected, "account:one:refresh") == "refresh-secret"
    with pytest.raises(RuntimeError, match="could not be unlocked"):
        TokenCipher.decrypt(protected, "account:two:refresh")


def test_cipher_reads_legacy_dpapi_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TokenCipher, "_backend", FakeDPAPI)
    legacy_blob = FakeDPAPI.CryptProtectData(b"legacy-token", TokenCipher.LEGACY_DESCRIPTION, None, None, None, 0)
    legacy_value = base64.b64encode(legacy_blob).decode("ascii")

    assert TokenCipher.needs_upgrade(legacy_value)
    assert TokenCipher.decrypt(legacy_value, "ignored-purpose") == "legacy-token"


def test_portable_cipher_round_trip_is_bound_to_purpose(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(TokenCipher, "_backend", None)
    monkeypatch.setattr(TokenCipher, "_keyring", None)
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")

    protected = TokenCipher.encrypt("refresh-secret", "account:one:refresh")

    assert protected.startswith(TokenCipher.PORTABLE_PREFIX)
    assert TokenCipher.decrypt(protected, "account:one:refresh") == "refresh-secret"
    assert (Paths.CONFIG_ROOT / "private" / "credential.key").is_file()
    with pytest.raises(RuntimeError, match="could not be unlocked"):
        TokenCipher.decrypt(protected, "account:two:refresh")


def test_portable_cipher_prefers_secret_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    keyring = FakeKeyring()
    monkeypatch.setattr(TokenCipher, "_backend", None)
    monkeypatch.setattr(TokenCipher, "_keyring", keyring)
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")

    protected = TokenCipher.encrypt("refresh-secret", "account:one:refresh")

    assert TokenCipher.decrypt(protected, "account:one:refresh") == "refresh-secret"
    assert not (Paths.CONFIG_ROOT / "private" / "credential.key").exists()
    assert keyring.values
    assert TokenCipher.protection_backend() == ("secret-service", True)


def test_portable_cipher_falls_back_when_secret_service_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(TokenCipher, "_backend", None)
    monkeypatch.setattr(TokenCipher, "_keyring", UnavailableKeyring())
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")

    protected = TokenCipher.encrypt("refresh-secret", "account:one:refresh")

    assert TokenCipher.decrypt(protected, "account:one:refresh") == "refresh-secret"
    assert (Paths.CONFIG_ROOT / "private" / "credential.key").is_file()
    assert TokenCipher.protection_backend() == ("encrypted-file", False)


def test_secret_service_migrates_existing_alpha2_key_without_rotating_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    keyring = FakeKeyring()
    old_key = Fernet.generate_key()
    key_path = tmp_path / "config" / "private" / "credential.key"
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(old_key)
    keyring.set_password(TokenCipher.KEYRING_SERVICE, TokenCipher.KEYRING_USERNAME, Fernet.generate_key().decode("ascii"))
    monkeypatch.setattr(TokenCipher, "_backend", None)
    monkeypatch.setattr(TokenCipher, "_keyring", keyring)
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")

    cipher = TokenCipher._portable_cipher()

    assert cipher.decrypt(cipher.encrypt(b"still-readable")) == b"still-readable"
    assert keyring.get_password(TokenCipher.KEYRING_SERVICE, TokenCipher.KEYRING_USERNAME) == old_key.decode("ascii")
    assert not key_path.exists()
