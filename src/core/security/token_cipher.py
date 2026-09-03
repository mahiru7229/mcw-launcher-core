from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from src.config import LAUNCHER_SLUG, MICROSOFT_CLIENT_ID
from src.core.fs.paths import Paths

try:
    import win32crypt as _win32crypt
except ImportError:  # pragma: no cover - Windows runtime dependency
    _win32crypt = None

try:
    import keyring as _keyring
except ImportError:  # pragma: no cover - optional Linux desktop dependency
    _keyring = None


class TokenCipher:
    DPAPI_PREFIX = "mcw-dpapi:v2:"
    PORTABLE_PREFIX = "mcw-fernet:v1:"
    PREFIX = DPAPI_PREFIX  # compatibility alias
    LEGACY_DESCRIPTION = "Zen Launcher Token"
    DESCRIPTION = "MCW Launcher Protected Token"
    VERSION = 2
    _backend: Any = _win32crypt
    _keyring: Any = _keyring
    _portable_backend_name = "encrypted-file"
    KEYRING_SERVICE = f"{LAUNCHER_SLUG}.credentials"
    KEYRING_USERNAME = "fernet-key-v1"

    @classmethod
    def encrypt(cls, value: str, purpose: str = "generic") -> str:
        if not value:
            return ""
        if cls._backend is not None:
            return cls._encrypt_dpapi(value, purpose)
        return cls._encrypt_portable(value, purpose)

    @classmethod
    def decrypt(cls, value: str, purpose: str = "generic") -> str:
        if not value:
            return ""
        if value.startswith(cls.PORTABLE_PREFIX):
            return cls._decrypt_portable(value, purpose)
        if cls._backend is not None:
            return cls._decrypt_dpapi(value, purpose)
        raise RuntimeError(
            "Stored credentials use Windows DPAPI and cannot be unlocked on this platform. "
            "Sign in again on this device."
        )

    @classmethod
    def _encrypt_dpapi(cls, value: str, purpose: str) -> str:
        backend = cls._backend
        try:
            encrypted_data = backend.CryptProtectData(
                value.encode("utf-8"),
                cls.DESCRIPTION,
                cls._entropy(purpose),
                None,
                None,
                getattr(backend, "CRYPTPROTECT_UI_FORBIDDEN", 0x1),
            )
            return f"{cls.DPAPI_PREFIX}{base64.b64encode(encrypted_data).decode('ascii')}"
        except Exception as error:
            raise RuntimeError("Failed to protect Microsoft account credentials.") from error

    @classmethod
    def _decrypt_dpapi(cls, value: str, purpose: str) -> str:
        backend = cls._backend
        try:
            if value.startswith(cls.DPAPI_PREFIX):
                encrypted_data = base64.b64decode(value[len(cls.DPAPI_PREFIX):], validate=True)
                _, decrypted_data = backend.CryptUnprotectData(
                    encrypted_data,
                    cls._entropy(purpose),
                    None,
                    None,
                    getattr(backend, "CRYPTPROTECT_UI_FORBIDDEN", 0x1),
                )
            else:
                encrypted_data = base64.b64decode(value, validate=True)
                _, decrypted_data = backend.CryptUnprotectData(encrypted_data, None, None, None, 0)
            return decrypted_data.decode("utf-8")
        except Exception as error:
            raise RuntimeError("Stored Microsoft account credentials could not be unlocked on this Windows account.") from error

    @classmethod
    def _encrypt_portable(cls, value: str, purpose: str) -> str:
        payload = json.dumps(
            {"purpose": cls._normalized_purpose(purpose), "value": value},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = cls._portable_cipher().encrypt(payload).decode("ascii")
        return f"{cls.PORTABLE_PREFIX}{encrypted}"

    @classmethod
    def _decrypt_portable(cls, value: str, purpose: str) -> str:
        try:
            encrypted = value[len(cls.PORTABLE_PREFIX):].encode("ascii")
            payload = json.loads(cls._portable_cipher().decrypt(encrypted).decode("utf-8"))
            if payload.get("purpose") != cls._normalized_purpose(purpose):
                raise InvalidToken
            plaintext = payload.get("value")
            if not isinstance(plaintext, str):
                raise InvalidToken
            return plaintext
        except (InvalidToken, ValueError, UnicodeError, json.JSONDecodeError, OSError) as error:
            raise RuntimeError(
                "Stored credentials could not be unlocked for this Linux user. Sign in again."
            ) from error

    @classmethod
    def _portable_cipher(cls) -> Fernet:
        key_path = cls._portable_key_path()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        file_key = cls._read_portable_key(key_path)

        if cls._keyring is not None:
            try:
                stored = cls._keyring.get_password(cls.KEYRING_SERVICE, cls.KEYRING_USERNAME)
                keyring_key = stored.encode("ascii") if isinstance(stored, str) else b""
                if file_key is not None:
                    # Alpha 2 stored this key beside the portable config. Seed
                    # the exact key into Secret Service so existing encrypted
                    # tokens remain readable, then remove the disk copy.
                    if keyring_key != file_key:
                        cls._keyring.set_password(cls.KEYRING_SERVICE, cls.KEYRING_USERNAME, file_key.decode("ascii"))
                    key_path.unlink(missing_ok=True)
                    cls._portable_backend_name = "secret-service"
                    return Fernet(file_key)
                if cls._valid_fernet_key(keyring_key):
                    cls._portable_backend_name = "secret-service"
                    return Fernet(keyring_key)

                selected = Fernet.generate_key()
                cls._keyring.set_password(cls.KEYRING_SERVICE, cls.KEYRING_USERNAME, selected.decode("ascii"))
                cls._portable_backend_name = "secret-service"
                return Fernet(selected)
            except Exception:
                # Secret Service may be unavailable or locked in a minimal
                # desktop session. Keep the encrypted-file fallback usable.
                pass

        cls._portable_backend_name = "encrypted-file"
        key = file_key
        if key is None:
            key = Fernet.generate_key()
            try:
                descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                key = cls._read_portable_key(key_path) or b""
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(key)
                    stream.flush()
                    os.fsync(stream.fileno())
        if os.name != "nt":
            key_path.chmod(0o600)
        try:
            return Fernet(key)
        except (ValueError, TypeError) as error:
            raise RuntimeError("The local credential key is invalid.") from error

    @staticmethod
    def _read_portable_key(path: Path) -> bytes | None:
        try:
            key = path.read_bytes().strip()
        except (FileNotFoundError, OSError):
            return None
        return key if TokenCipher._valid_fernet_key(key) else None

    @staticmethod
    def _valid_fernet_key(key: bytes) -> bool:
        if not key:
            return False
        try:
            Fernet(key)
        except (ValueError, TypeError):
            return False
        return True

    @classmethod
    def protection_backend(cls) -> tuple[str, bool]:
        if cls._backend is not None:
            return "windows-dpapi", True
        # Resolve the optional desktop keyring before reporting status. This
        # keeps Account Security accurate even before the first Microsoft
        # token is stored in the current session.
        cls._portable_cipher()
        return cls._portable_backend_name, cls._portable_backend_name == "secret-service"

    @staticmethod
    def _portable_key_path() -> Path:
        return Paths.CONFIG_ROOT / "private" / "credential.key"

    @classmethod
    def needs_upgrade(cls, value: str | None) -> bool:
        return bool(value) and not str(value).startswith((cls.DPAPI_PREFIX, cls.PORTABLE_PREFIX))

    @classmethod
    def version_of(cls, value: str | None) -> int:
        if not value:
            return cls.VERSION
        return cls.VERSION if str(value).startswith((cls.DPAPI_PREFIX, cls.PORTABLE_PREFIX)) else 1

    @classmethod
    def _entropy(cls, purpose: str) -> bytes:
        context = f"{LAUNCHER_SLUG}|{MICROSOFT_CLIENT_ID}|{cls._normalized_purpose(purpose)}"
        return hashlib.sha256(context.encode("utf-8")).digest()

    @staticmethod
    def _normalized_purpose(purpose: str) -> str:
        return str(purpose or "generic").strip().casefold()
