from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3

from src.core.security.token_cipher import TokenCipher


class AccountIntegrityError(RuntimeError):
    pass


class AccountIntegrity:
    STATE_KEY = "security.account_integrity_key.v1"
    KEY_PURPOSE = "account-integrity-key"

    @classmethod
    def get_or_create_key(cls, connection: sqlite3.Connection) -> bytes:
        row = connection.execute("SELECT value FROM account_state WHERE key = ?", (cls.STATE_KEY,)).fetchone()
        if row is not None and row["value"]:
            encoded = TokenCipher.decrypt(str(row["value"]), cls.KEY_PURPOSE)
            try:
                key = base64.urlsafe_b64decode(encoded.encode("ascii"))
            except Exception as error:
                raise AccountIntegrityError("The account integrity key is invalid.") from error
            if len(key) < 32:
                raise AccountIntegrityError("The account integrity key is invalid.")
            return key

        key = secrets.token_bytes(32)
        protected = TokenCipher.encrypt(base64.urlsafe_b64encode(key).decode("ascii"), cls.KEY_PURPOSE)
        connection.execute(
            "INSERT INTO account_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (cls.STATE_KEY, protected),
        )
        return key


    @classmethod
    def reset_key(cls, connection: sqlite3.Connection) -> bytes:
        connection.execute("DELETE FROM account_state WHERE key = ?", (cls.STATE_KEY,))
        return cls.get_or_create_key(connection)

    @classmethod
    def sign(cls, key: bytes, payload: dict) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(key, canonical, hashlib.sha256).hexdigest()

    @classmethod
    def verify(cls, key: bytes, payload: dict, signature: str | None) -> bool:
        if not signature:
            return False
        return hmac.compare_digest(cls.sign(key, payload), str(signature))
