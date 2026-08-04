from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import os

import httpx

from src.core.fs.paths import Paths
from src.models.account.account import Account
from src.models.auth.microsoft.minecraft_profile import MinecraftProfile


class AccountSkinManager:
    """Cache Minecraft skin textures without making the GUI depend on network APIs."""

    MAX_TEXTURE_BYTES = 4 * 1024 * 1024
    REQUEST_TIMEOUT_SECONDS = 20.0
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    @classmethod
    def cache_profile(cls, profile: MinecraftProfile) -> Path | None:
        skin_url = profile.primary_skin_url
        if not skin_url:
            return None
        return cls.cache_texture(profile.profile_id, skin_url)

    @classmethod
    def cache_account(cls, account: Account) -> Path | None:
        skin_url = str(account.skin_url or "").strip()
        if not skin_url:
            return None
        return cls.cache_texture(account.uuid, skin_url)

    @classmethod
    def cache_texture(cls, profile_uuid: str, skin_url: str) -> Path:
        normalized_uuid = cls._normalize_uuid(profile_uuid)
        normalized_url = cls._validate_url(skin_url)
        target = cls.texture_path(normalized_uuid)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            with httpx.stream("GET", normalized_url, headers={"Accept": "image/png"}, timeout=cls.REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as response:
                response.raise_for_status()
                total = 0
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes(64 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > cls.MAX_TEXTURE_BYTES:
                            raise RuntimeError("Minecraft skin texture exceeds the 4 MiB safety limit.")
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

            if temporary.stat().st_size < len(cls.PNG_SIGNATURE):
                raise RuntimeError("Minecraft Services returned an empty skin texture.")
            with temporary.open("rb") as texture:
                if texture.read(len(cls.PNG_SIGNATURE)) != cls.PNG_SIGNATURE:
                    raise RuntimeError("Minecraft Services returned an invalid skin texture.")
            temporary.replace(target)
            return target
        except (httpx.HTTPError, OSError, RuntimeError) as error:
            temporary.unlink(missing_ok=True)
            if isinstance(error, RuntimeError):
                raise
            raise RuntimeError("Unable to cache the Minecraft skin texture.") from error

    @classmethod
    def cached_texture(cls, account_or_uuid: Account | str) -> Path | None:
        profile_uuid = account_or_uuid.uuid if isinstance(account_or_uuid, Account) else str(account_or_uuid)
        try:
            path = cls.texture_path(profile_uuid)
        except ValueError:
            return None
        return path if path.is_file() else None

    @classmethod
    def remove_cached_texture(cls, account_or_uuid: Account | str) -> None:
        path = cls.cached_texture(account_or_uuid)
        if path is not None:
            path.unlink(missing_ok=True)

    @staticmethod
    def texture_path(profile_uuid: str) -> Path:
        normalized_uuid = AccountSkinManager._normalize_uuid(profile_uuid)
        return Paths.account_skins_root() / f"{normalized_uuid}.png"

    @staticmethod
    def _normalize_uuid(value: str) -> str:
        normalized = str(value or "").replace("-", "").strip().casefold()
        if len(normalized) != 32 or any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("Minecraft profile UUID is invalid.")
        return normalized

    @staticmethod
    def _validate_url(value: str) -> str:
        url = str(value or "").strip()
        parsed = urlparse(url)
        if parsed.scheme.casefold() != "https" or not parsed.netloc:
            raise ValueError("Minecraft skin URL must use HTTPS.")
        return url
