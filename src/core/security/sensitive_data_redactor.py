from __future__ import annotations

import json
import re
from typing import Any


class SensitiveDataRedactor:
    REDACTED = "<redacted>"

    _SENSITIVE_KEYS = {
        "access_token",
        "refresh_token",
        "authorization",
        "code",
        "code_verifier",
        "client_secret",
        "password",
        "token",
        "xsts_token",
        "xbox_token",
    }

    _BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
    _ASSIGNMENT_PATTERN = re.compile(
        r"(?i)(\b(?:access_token|refresh_token|authorization|code|code_verifier|client_secret|password|xsts_token|xbox_token|token)\b\s*[:=]\s*)([^\s,&;\]\}\"']+|\"[^\"]*\"|'[^']*')"
    )
    _QUERY_PATTERN = re.compile(
        r"(?i)([?&](?:access_token|refresh_token|code|code_verifier|client_secret|token)=)([^&#\s]+)"
    )
    _JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

    @classmethod
    def redact_text(cls, value: object) -> str:
        text = str(value or "")
        text = cls._BEARER_PATTERN.sub(f"Bearer {cls.REDACTED}", text)
        text = cls._QUERY_PATTERN.sub(lambda match: f"{match.group(1)}{cls.REDACTED}", text)
        text = cls._ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}{cls.REDACTED}", text)
        text = cls._JWT_PATTERN.sub(cls.REDACTED, text)
        return text

    @classmethod
    def redact_value(cls, value: Any, key: str = "") -> Any:
        if str(key).casefold() in cls._SENSITIVE_KEYS:
            return cls.REDACTED
        if isinstance(value, dict):
            return {str(item_key): cls.redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
        if isinstance(value, list):
            return [cls.redact_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls.redact_value(item) for item in value)
        if isinstance(value, str):
            return cls.redact_text(value)
        return value

    @classmethod
    def redact_json(cls, value: Any) -> str:
        return json.dumps(cls.redact_value(value), ensure_ascii=False, sort_keys=True)
