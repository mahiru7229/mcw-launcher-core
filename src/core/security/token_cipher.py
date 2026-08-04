from __future__ import annotations

import base64
import hashlib
from typing import Any

from src.config import LAUNCHER_SLUG, MICROSOFT_CLIENT_ID

try:
    import win32crypt as _win32crypt
except ImportError:  # pragma: no cover - Windows runtime dependency
    _win32crypt = None


class TokenCipher:
    PREFIX = "mcw-dpapi:v2:"
    LEGACY_DESCRIPTION = "Zen Launcher Token"
    DESCRIPTION = "MCW Launcher Protected Token"
    VERSION = 2
    _backend: Any = _win32crypt

    @classmethod
    def encrypt(cls, value: str, purpose: str = "generic") -> str:
        if not value:
            return ""
        backend = cls._require_backend()
        try:
            encrypted_data = backend.CryptProtectData(
                value.encode("utf-8"),
                cls.DESCRIPTION,
                cls._entropy(purpose),
                None,
                None,
                getattr(backend, "CRYPTPROTECT_UI_FORBIDDEN", 0x1),
            )
            encoded = base64.b64encode(encrypted_data).decode("ascii")
            return f"{cls.PREFIX}{encoded}"
        except Exception as error:
            raise RuntimeError("Failed to protect Microsoft account credentials.") from error

    @classmethod
    def decrypt(cls, value: str, purpose: str = "generic") -> str:
        if not value:
            return ""
        backend = cls._require_backend()
        try:
            if value.startswith(cls.PREFIX):
                encrypted_data = base64.b64decode(value[len(cls.PREFIX):], validate=True)
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
    def needs_upgrade(cls, value: str | None) -> bool:
        return bool(value) and not str(value).startswith(cls.PREFIX)

    @classmethod
    def version_of(cls, value: str | None) -> int:
        if not value:
            return cls.VERSION
        return cls.VERSION if str(value).startswith(cls.PREFIX) else 1

    @classmethod
    def _entropy(cls, purpose: str) -> bytes:
        context = f"{LAUNCHER_SLUG}|{MICROSOFT_CLIENT_ID}|{str(purpose or 'generic').strip().casefold()}"
        return hashlib.sha256(context.encode("utf-8")).digest()

    @classmethod
    def _require_backend(cls):
        if cls._backend is None:
            raise RuntimeError("Microsoft account credential protection requires pywin32 on Windows.")
        return cls._backend
