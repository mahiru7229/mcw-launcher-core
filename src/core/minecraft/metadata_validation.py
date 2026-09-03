from __future__ import annotations

from pathlib import Path
import re


class MinecraftMetadataValidation:
    """Validate untrusted path and digest fields from Minecraft metadata."""

    _IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
    # Mojang's official manifest includes legacy names such as
    # ``1.14.2 Pre-Release 4`` and ``3D Shareware v1.34``. Spaces are valid in
    # those IDs, while separators, drive prefixes and control characters are
    # still rejected so an ID remains safe as a local directory/file name.
    _VERSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+ -]{0,159}$")
    # Mojang publishes 40-character SHA-1 values. A shorter lower bound keeps
    # legacy/custom metadata parseable while still preventing path separators
    # and non-hexadecimal content from reaching cache paths.
    _SHA1_PATTERN = re.compile(r"^[0-9a-fA-F]{6,40}$")

    @classmethod
    def relative_path(cls, value: object, label: str = "metadata path") -> Path:
        normalized = str(value or "").replace("\\", "/").strip()
        segments = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or len(normalized) > 1024
            or any(not segment or segment in {".", ".."} for segment in segments)
            or any(":" in segment or "\x00" in segment for segment in segments)
        ):
            raise RuntimeError(f"Unsafe {label}: {value!r}")
        return Path(*segments)

    @classmethod
    def identifier(cls, value: object, label: str = "metadata identifier") -> str:
        normalized = str(value or "").strip()
        if not cls._IDENTIFIER_PATTERN.fullmatch(normalized) or normalized in {".", ".."}:
            raise RuntimeError(f"Unsafe {label}: {value!r}")
        return normalized

    @classmethod
    def version_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not cls._VERSION_ID_PATTERN.fullmatch(normalized) or normalized in {".", ".."}:
            raise RuntimeError(f"Unsafe Minecraft version id: {value!r}")
        return normalized

    @classmethod
    def sha1(cls, value: object, label: str = "SHA-1") -> str:
        normalized = str(value or "").strip().casefold()
        if not cls._SHA1_PATTERN.fullmatch(normalized):
            raise RuntimeError(f"Invalid {label}: {value!r}")
        return normalized
