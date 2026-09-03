from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse
import json
import os

from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL
from src.core.fs.paths import Paths
from src.core.security.token_cipher import TokenCipher


class CurseForgeConfigManager:
    """Loads CurseForge gateway endpoints with safe local overrides.

    The public MCW gateway is the default on fresh installations. User-provided
    overrides are protected with Windows DPAPI and environment variables remain
    available for managed deployments. No CurseForge API credential is stored in
    the launcher.
    """

    SCHEMA_VERSION = 3
    MAX_GATEWAYS = 5
    PURPOSE_PREFIX = "curseforge:gateway"
    TOKEN_PURPOSE = "curseforge:client-token"

    ENV_GATEWAY_URL = "MCW_CURSEFORGE_GATEWAY_URL"  # Legacy single endpoint.
    ENV_GATEWAY_URL_PREFIX = "MCW_CURSEFORGE_GATEWAY_URL_"
    ENV_CLIENT_TOKEN = "MCW_CURSEFORGE_CLIENT_TOKEN"
    DEFAULT_GATEWAY_URLS = (CURSEFORGE_DEFAULT_GATEWAY_URL,)

    @staticmethod
    def path() -> Path:
        return Paths.CONFIG_ROOT / "private" / "curseforge_endpoints.json"

    @staticmethod
    def legacy_path() -> Path:
        return Paths.CONFIG_ROOT / "curseforge.json"

    @classmethod
    def gateway_urls(cls) -> tuple[str, ...]:
        environment = cls._environment_gateway_urls()
        if environment:
            return environment

        data = cls._load()
        protected = data.get("protected_gateway_urls")
        if isinstance(protected, list):
            values: list[str] = []
            for index, value in enumerate(protected[: cls.MAX_GATEWAYS], start=1):
                if not str(value or "").strip():
                    continue
                try:
                    plaintext = TokenCipher.decrypt(str(value), cls._gateway_purpose(index))
                except RuntimeError as error:
                    raise RuntimeError("Stored CurseForge gateway links could not be unlocked on this Windows account.") from error
                values.append(plaintext)
            return cls._normalize_urls(values)

        # Legacy/plaintext formats remain readable for migration. The next save
        # rewrites them using DPAPI protection.
        legacy_values = data.get("gateway_urls")
        if isinstance(legacy_values, list):
            normalized = cls._normalize_urls(legacy_values)
            if normalized:
                return normalized
        legacy_single = str(data.get("gateway_url") or "").strip()
        if legacy_single:
            return cls._normalize_urls([legacy_single])
        return cls._normalize_urls(cls.DEFAULT_GATEWAY_URLS)

    @classmethod
    def gateway_url(cls) -> str:
        urls = cls.gateway_urls()
        if not urls:
            raise ValueError("At least one CurseForge gateway URL must be configured.")
        return urls[0]

    @classmethod
    def client_token(cls) -> str:
        environment = str(os.environ.get(cls.ENV_CLIENT_TOKEN) or "").strip()
        return environment or cls._stored_client_token()

    @classmethod
    def _stored_client_token(cls) -> str:
        data = cls._load()
        protected = str(data.get("protected_client_token") or "").strip()
        if protected:
            try:
                return TokenCipher.decrypt(protected, cls.TOKEN_PURPOSE).strip()
            except RuntimeError as error:
                raise RuntimeError("The stored CurseForge client token could not be unlocked on this Windows account.") from error
        return str(data.get("client_token") or "").strip()

    @classmethod
    def is_configured(cls) -> bool:
        try:
            return bool(cls.gateway_urls())
        except (RuntimeError, ValueError):
            return False

    @classmethod
    def save_local(cls, gateway_urls: Iterable[str] | str, client_token: str | None = None) -> Path:
        values = [gateway_urls] if isinstance(gateway_urls, str) else list(gateway_urls)
        nonempty_values = [value for value in values if str(value or "").strip()]
        if len(nonempty_values) > cls.MAX_GATEWAYS:
            raise ValueError(f"At most {cls.MAX_GATEWAYS} CurseForge gateway URLs can be configured.")
        normalized = cls._normalize_urls(nonempty_values)

        existing_token = cls._stored_client_token() if client_token is None else str(client_token).strip()
        path = cls.path()
        if not normalized and not existing_token:
            cls._remove_local_files(path)
            return path

        try:
            protected_urls = [
                TokenCipher.encrypt(value, cls._gateway_purpose(index))
                for index, value in enumerate(normalized, start=1)
            ]
            protected_token = TokenCipher.encrypt(existing_token, cls.TOKEN_PURPOSE) if existing_token else ""
        except RuntimeError as error:
            raise RuntimeError("CurseForge gateway links could not be protected with Windows DPAPI.") from error

        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": cls.SCHEMA_VERSION,
                    "protected_gateway_urls": protected_urls,
                    "protected_client_token": protected_token,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        cls._remove_legacy_file(path)
        return path


    @classmethod
    def _remove_local_files(cls, current_path: Path) -> None:
        for candidate in (current_path, cls.legacy_path()):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass

    @classmethod
    def _remove_legacy_file(cls, current_path: Path) -> None:
        legacy = cls.legacy_path()
        if legacy == current_path:
            return
        try:
            legacy.unlink()
        except FileNotFoundError:
            pass

    @classmethod
    def _environment_gateway_urls(cls) -> tuple[str, ...]:
        indexed = [
            str(os.environ.get(f"{cls.ENV_GATEWAY_URL_PREFIX}{index}") or "").strip()
            for index in range(1, cls.MAX_GATEWAYS + 1)
        ]
        indexed = [value for value in indexed if value]
        if indexed:
            return cls._normalize_urls(indexed)
        legacy = str(os.environ.get(cls.ENV_GATEWAY_URL) or "").strip()
        return cls._normalize_urls([legacy]) if legacy else ()

    @classmethod
    def _load(cls) -> dict:
        for path in (cls.path(), cls.legacy_path()):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
        return {}

    @classmethod
    def _normalize_urls(cls, values: Iterable[object]) -> tuple[str, ...]:
        output: list[str] = []
        for value in values:
            raw = str(value or "").strip()
            if not raw:
                continue
            normalized = cls._normalize_url(raw)
            if normalized not in output:
                output.append(normalized)
            if len(output) >= cls.MAX_GATEWAYS:
                break
        return tuple(output)

    @staticmethod
    def _normalize_url(value: str) -> str:
        normalized = str(value).strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("CurseForge gateway URL must be a valid HTTPS URL.")
        if parsed.username or parsed.password:
            raise ValueError("CurseForge gateway URLs must not contain embedded credentials.")
        return normalized

    @classmethod
    def _gateway_purpose(cls, index: int) -> str:
        return f"{cls.PURPOSE_PREFIX}:{int(index)}"
