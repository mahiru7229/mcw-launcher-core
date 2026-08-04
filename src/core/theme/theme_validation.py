from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from src.core.theme.theme_contract import THEME_RUNTIME_CONTRACT_VERSION, THEME_VALIDATION_REPORT_VERSION
from src.core.theme.theme_manager import ThemeError, ThemeManager, theme_manager


class ThemeValidationCode:
    THEME_NOT_INSTALLED = "THEME_NOT_INSTALLED"
    THEME_MANIFEST_MISSING = "THEME_MANIFEST_MISSING"
    THEME_MANIFEST_INVALID_JSON = "THEME_MANIFEST_INVALID_JSON"
    THEME_MANIFEST_INVALID_ROOT = "THEME_MANIFEST_INVALID_ROOT"
    THEME_SCHEMA_INVALID = "THEME_SCHEMA_INVALID"
    THEME_SCHEMA_UNSUPPORTED = "THEME_SCHEMA_UNSUPPORTED"
    THEME_ID_INVALID = "THEME_ID_INVALID"
    THEME_ASSET_UNKNOWN_KEY = "THEME_ASSET_UNKNOWN_KEY"
    THEME_ASSET_MISSING_FILE = "THEME_ASSET_MISSING_FILE"
    THEME_ASSET_INVALID_PNG = "THEME_ASSET_INVALID_PNG"
    THEME_ASSET_UNSAFE_PATH = "THEME_ASSET_UNSAFE_PATH"
    THEME_TEXT_ASSET_INVALID = "THEME_TEXT_ASSET_INVALID"
    THEME_ANIMATION_INVALID = "THEME_ANIMATION_INVALID"
    THEME_ANIMATION_SHEET_TOO_SMALL = "THEME_ANIMATION_SHEET_TOO_SMALL"
    THEME_FONT_INVALID = "THEME_FONT_INVALID"
    THEME_MOTION_INVALID = "THEME_MOTION_INVALID"
    THEME_PALETTE_INVALID = "THEME_PALETTE_INVALID"
    THEME_ACCENT_ASSET_INVALID = "THEME_ACCENT_ASSET_INVALID"
    THEME_STYLESHEET_INVALID = "THEME_STYLESHEET_INVALID"
    THEME_CAPABILITY_INVALID = "THEME_CAPABILITY_INVALID"
    THEME_SECURITY_VIOLATION = "THEME_SECURITY_VIOLATION"
    THEME_UNKNOWN_ISSUE = "THEME_UNKNOWN_ISSUE"


@dataclass(frozen=True)
class ThemeValidationIssue:
    # Keep the first three positional fields compatible with Beta 2.
    severity: str
    category: str
    message: str
    code: str = ThemeValidationCode.THEME_UNKNOWN_ISSUE
    field: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "severity": self.severity,
            "category": self.category,
            "code": self.code,
            "message": self.message,
        }
        if self.field:
            payload["field"] = self.field
        if self.path:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class ThemeValidationReport:
    theme_id: str
    name: str
    root: Path | None
    issues: tuple[ThemeValidationIssue, ...]
    schema_version: int | None = None
    report_version: int = THEME_VALIDATION_REPORT_VERSION
    contract_version: int = THEME_RUNTIME_CONTRACT_VERSION

    @property
    def error_count(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "report_version": self.report_version,
            "contract_version": self.contract_version,
            "theme_id": self.theme_id,
            "name": self.name,
            "valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }
        if self.schema_version is not None:
            payload["schema_version"] = self.schema_version
        if self.root is not None:
            payload["root"] = str(self.root)
        return payload


class ThemeValidator:
    def __init__(self, manager: ThemeManager | None = None) -> None:
        self.manager = manager or theme_manager

    def validate(self, theme_id: str) -> ThemeValidationReport:
        normalized = str(theme_id or "").strip()
        definition = next((theme for theme in self.manager.available_themes() if theme.theme_id == normalized), None)
        if definition is None:
            issue = ThemeValidationIssue(
                "error",
                "manifest",
                f"Theme is not installed: {theme_id}",
                ThemeValidationCode.THEME_NOT_INSTALLED,
                "id",
            )
            return ThemeValidationReport(normalized, normalized, None, (issue,))
        if definition.root is None:
            return ThemeValidationReport(definition.theme_id, definition.name, None, (), definition.schema_version)
        return self.validate_directory(definition.root)

    def validate_directory(self, root: Path) -> ThemeValidationReport:
        directory = Path(root).resolve()
        try:
            definition = self.manager._load_theme(directory)
        except ThemeError as error:
            issue = self.issue_from_message(str(error))
            return ThemeValidationReport(directory.name, directory.name, directory, (issue,), self._read_schema_version(directory))
        issues = tuple(self.issue_from_message(message) for message in definition.issues)
        if definition.schema_version == self.manager.LATEST_SCHEMA_VERSION:
            strict_codes = {
                ThemeValidationCode.THEME_ASSET_UNKNOWN_KEY,
                ThemeValidationCode.THEME_TEXT_ASSET_INVALID,
                ThemeValidationCode.THEME_CAPABILITY_INVALID,
                ThemeValidationCode.THEME_ACCENT_ASSET_INVALID,
            }
            issues = tuple(
                ThemeValidationIssue("error", issue.category, issue.message, issue.code, issue.field, issue.path)
                if issue.code in strict_codes else issue
                for issue in issues
            )
        return ThemeValidationReport(definition.theme_id, definition.name, definition.root, issues, definition.schema_version)

    @classmethod
    def issue_from_message(cls, message: str) -> ThemeValidationIssue:
        lowered = message.casefold()
        category = cls._category(message)
        severity = "warning" if lowered.startswith("unknown ") or "capabilities must" in lowered else "error"
        code = ThemeValidationCode.THEME_UNKNOWN_ISSUE
        field: str | None = None
        path: str | None = None

        if "missing theme.json" in lowered:
            code = ThemeValidationCode.THEME_MANIFEST_MISSING
        elif "unable to read theme manifest" in lowered:
            code = ThemeValidationCode.THEME_MANIFEST_INVALID_JSON
        elif "manifest root must be an object" in lowered:
            code = ThemeValidationCode.THEME_MANIFEST_INVALID_ROOT
        elif "unsupported theme schema version" in lowered:
            code = ThemeValidationCode.THEME_SCHEMA_UNSUPPORTED
            field = "schema_version"
        elif "schema_version must be an integer" in lowered:
            code = ThemeValidationCode.THEME_SCHEMA_INVALID
            field = "schema_version"
        elif "theme schema 6" in lowered:
            code = ThemeValidationCode.THEME_SCHEMA_INVALID
            if "requires id" in lowered:
                field = "id"
            else:
                match = re.search(r"field:\s*([A-Za-z0-9_$.-]+)", message)
                field = match.group(1) if match else None
        elif "theme id is invalid" in lowered:
            code = ThemeValidationCode.THEME_ID_INVALID
            field = "id"
        elif lowered.startswith("unknown accent asset key:"):
            code = ThemeValidationCode.THEME_ACCENT_ASSET_INVALID
            key = message.split(":", 1)[1].strip()
            field = "accent_assets"
            path = key or None
        elif "theme palette" in lowered:
            code = ThemeValidationCode.THEME_PALETTE_INVALID
            field = "palette"
        elif lowered.startswith("unknown asset key:"):
            code = ThemeValidationCode.THEME_ASSET_UNKNOWN_KEY
            key = message.split(":", 1)[1].strip()
            field = f"assets.{key}" if key else "assets"
        elif "theme asset file is missing" in lowered:
            code = ThemeValidationCode.THEME_ASSET_MISSING_FILE
            field, path = cls._field_and_path(message, "assets")
        elif "invalid png" in lowered or "invalid png dimensions" in lowered:
            code = ThemeValidationCode.THEME_ASSET_INVALID_PNG
            path = cls._trailing_path(message)
        elif "unknown text asset key" in lowered or "invalid static text role" in lowered:
            code = ThemeValidationCode.THEME_TEXT_ASSET_INVALID
            field = "text_assets"
        elif "sprite sheet is too small" in lowered:
            code = ThemeValidationCode.THEME_ANIMATION_SHEET_TOO_SMALL
            field = cls._animation_field(message)
            path = cls._path_after_colon(message)
        elif "animation" in lowered or "sprite" in lowered:
            code = ThemeValidationCode.THEME_ANIMATION_INVALID
            field = cls._animation_field(message)
        elif "font" in lowered:
            code = ThemeValidationCode.THEME_FONT_INVALID
            field = "font"
            path = cls._trailing_path(message)
        elif "motion" in lowered:
            code = ThemeValidationCode.THEME_MOTION_INVALID
            field = cls._motion_field(message)
        elif "stylesheet" in lowered or "qss" in lowered:
            code = ThemeValidationCode.THEME_STYLESHEET_INVALID
            field = "stylesheet"
            path = cls._trailing_path(message)
        elif "capabilities must" in lowered:
            code = ThemeValidationCode.THEME_CAPABILITY_INVALID
            field = "capabilities"
        elif any(token in lowered for token in ("unsafe", "escapes its theme directory", "symbolic link", "path escapes")):
            code = ThemeValidationCode.THEME_SECURITY_VIOLATION
            path = cls._quoted_value(message) or cls._trailing_path(message)
        elif "asset" in lowered:
            code = ThemeValidationCode.THEME_ASSET_MISSING_FILE if "missing" in lowered else ThemeValidationCode.THEME_UNKNOWN_ISSUE
            field = "assets"

        # Unsafe paths are security issues even when a more specific parser branch
        # also identified the affected field.
        if any(token in lowered for token in ("unsafe", "escapes its theme directory", "path escapes")):
            code = ThemeValidationCode.THEME_ASSET_UNSAFE_PATH if category in {"asset", "animation", "font", "style"} else ThemeValidationCode.THEME_SECURITY_VIOLATION

        return ThemeValidationIssue(severity, category, message, code, field, path)

    @staticmethod
    def _read_schema_version(directory: Path) -> int | None:
        try:
            payload = json.loads((directory / "theme.json").read_text(encoding="utf-8-sig"))
            return int(payload.get("schema_version", 1)) if isinstance(payload, dict) else None
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return None

    @staticmethod
    def _category(message: str) -> str:
        lowered = message.casefold()
        if "palette" in lowered or "accent asset" in lowered:
            return "palette"
        if "font" in lowered:
            return "font"
        if "animation" in lowered or "sprite" in lowered:
            return "animation"
        if "motion" in lowered:
            return "motion"
        if "stylesheet" in lowered or "qss" in lowered:
            return "style"
        if "path" in lowered or "escapes" in lowered or "unsafe" in lowered or "symbolic" in lowered:
            return "security"
        if "manifest" in lowered or "schema" in lowered or "theme id" in lowered:
            return "manifest"
        return "asset"

    @staticmethod
    def _quoted_value(message: str) -> str | None:
        match = re.search(r"['\"]([^'\"]+)['\"]", message)
        return match.group(1) if match else None

    @staticmethod
    def _trailing_path(message: str) -> str | None:
        candidate = message.rsplit(": ", 1)[-1].strip()
        return candidate if any(separator in candidate for separator in ("/", "\\")) else None

    @staticmethod
    def _path_after_colon(message: str) -> str | None:
        match = re.search(r":\s+([^()]+?)(?:\s+\(|$)", message)
        return match.group(1).strip() if match else None

    @staticmethod
    def _animation_field(message: str) -> str:
        match = re.search(r"[Aa]nimation\s+([a-z0-9._-]+)", message)
        return f"animations.{match.group(1)}" if match else "animations"

    @staticmethod
    def _motion_field(message: str) -> str:
        match = re.search(r"motion\s+([a-z0-9._-]+)", message, flags=re.IGNORECASE)
        return f"motion.{match.group(1)}" if match else "motion"

    @staticmethod
    def _field_and_path(message: str, default_field: str) -> tuple[str, str | None]:
        match = re.search(r"for\s+([a-z0-9._-]+):\s*(.+)$", message, flags=re.IGNORECASE)
        if not match:
            return default_field, None
        return f"{default_field}.{match.group(1)}", match.group(2).strip()
