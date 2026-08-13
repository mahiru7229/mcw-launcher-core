from __future__ import annotations

from pathlib import Path
import re
import tempfile
from typing import Any

from src.core.fs.paths import Paths
from src.core.security.sensitive_data_redactor import SensitiveDataRedactor


class DiagnosticsSanitizer:
    """Privacy sanitizer used only for exported diagnostics and issue payloads.

    The goal is to preserve useful relative paths while never publishing drive
    letters, UNC share names, home-directory names, or authentication secrets.
    """

    _DRIVE_PREFIX = re.compile(r"(?i)(?<![A-Za-z0-9])([A-Z]):[\\/]")
    _UNC_PREFIX = re.compile(r"(?<![\\/])\\\\[^\\/\r\n]+[\\/][^\\/\r\n]+[\\/]?")
    _UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
    _SERVER_PLAYER = re.compile(r"(?i)(ServerPlayer\[')([^']+)(')")
    _CLIENT_PLAYER = re.compile(r"(?i)(LocalPlayer\[')([^']+)(')")

    @classmethod
    def sanitize_path(cls, value: Path | str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        normalized = raw.replace("\\", "/")
        normalized_folded = normalized.casefold().rstrip("/")
        for root, alias in cls._known_roots():
            root_text = str(root).replace("\\", "/").rstrip("/")
            root_folded = root_text.casefold()
            if normalized_folded == root_folded:
                return f"{alias}/"
            prefix = root_folded + "/"
            if normalized.casefold().startswith(prefix):
                suffix = normalized[len(root_text):].lstrip("/")
                return f"{alias}/{suffix}" if suffix else f"{alias}/"
        if not cls._looks_windows_absolute(raw) and not normalized.startswith("/"):
            return normalized
        name = normalized.rstrip("/").rsplit("/", 1)[-1] or "path"
        return f"external/{name}"

    @classmethod
    def sanitize_text(cls, value: object, *, runtime_log: bool = False) -> str:
        text = SensitiveDataRedactor.redact_text(value)
        # Replace known roots first so useful relative context survives.
        for root, alias in cls._known_roots():
            variants = cls._root_variants(root)
            for variant in variants:
                if variant:
                    text = re.sub(re.escape(variant) + r"[\\/]?", f"{alias}/", text, flags=re.IGNORECASE)
        # Any remaining Windows absolute root becomes an anonymous root. This keeps
        # the relative tail but never exposes C:, D:, server names, or share names.
        text = cls._UNC_PREFIX.sub("root/", text)
        text = cls._DRIVE_PREFIX.sub("root/", text)
        if runtime_log:
            text = cls._SERVER_PLAYER.sub(r"\1<player>\3", text)
            text = cls._CLIENT_PLAYER.sub(r"\1<player>\3", text)
            text = cls._UUID.sub("<uuid>", text)
        # Normalize path separators only on lines where a path placeholder exists.
        lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if any(marker in line for marker in ("root/", "external/", "temp/", "user/")):
                line = line.replace("\\", "/")
                line = re.sub(r"(?<!:)/{2,}", "/", line)
            lines.append(line)
        return "".join(lines)

    @classmethod
    def sanitize_value(cls, value: Any, key: str = "") -> Any:
        redacted_scalar = SensitiveDataRedactor.redact_value(value, key)
        if redacted_scalar == SensitiveDataRedactor.REDACTED:
            return redacted_scalar
        lowered = str(key).casefold()
        if isinstance(value, dict):
            return {str(k): cls.sanitize_value(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [cls.sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls.sanitize_value(item) for item in value)
        if isinstance(value, Path):
            return cls.sanitize_path(value)
        if isinstance(value, str):
            if any(token in lowered for token in ("path", "dir", "directory", "executable", "java_home", "destination", "source")) and cls._looks_path(value):
                return cls.sanitize_path(value)
            return cls.sanitize_text(value)
        return SensitiveDataRedactor.redact_value(value, key)

    @classmethod
    def _known_roots(cls) -> tuple[tuple[Path, str], ...]:
        roots: list[tuple[Path, str]] = []
        try:
            roots.append((Path(Paths.SHORT_WORKSPACE_ROOT), "temp"))
        except Exception:
            pass
        try:
            roots.append((Path(Paths.root()), "root"))
        except Exception:
            pass
        try:
            roots.append((Path(tempfile.gettempdir()), "temp"))
        except Exception:
            pass
        try:
            roots.append((Path.home(), "user"))
        except Exception:
            pass
        # Longest roots first to avoid replacing a parent before a specific child.
        unique: dict[str, tuple[Path, str]] = {}
        for path, alias in roots:
            key = str(path).casefold()
            unique[key] = (path, alias)
        return tuple(sorted(unique.values(), key=lambda item: len(str(item[0])), reverse=True))

    @staticmethod
    def _root_variants(root: Path) -> tuple[str, ...]:
        raw = str(root)
        values = {raw.rstrip("\\/"), raw.replace("\\", "/").rstrip("/"), raw.replace("/", "\\").rstrip("\\")}
        return tuple(value for value in values if value)

    @staticmethod
    def _looks_windows_absolute(value: str) -> bool:
        return bool(re.match(r"(?i)^[A-Z]:[\\/]", value)) or value.startswith("\\\\")

    @classmethod
    def _looks_path(cls, value: str) -> bool:
        text = str(value or "").strip()
        return cls._looks_windows_absolute(text) or text.startswith("/") or "/" in text or "\\" in text
