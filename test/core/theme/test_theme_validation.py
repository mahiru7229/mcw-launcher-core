from __future__ import annotations

import json
from pathlib import Path

from src.core.theme.theme_manager import ThemeManager
from src.core.theme.theme_validation import ThemeValidationCode, ThemeValidator


def test_validation_report_exposes_stable_machine_readable_fields(tmp_path: Path) -> None:
    root = tmp_path / "themes" / "broken"
    root.mkdir(parents=True)
    (root / "theme.json").write_text(json.dumps({
        "schema_version": 6,
        "id": "broken",
        "assets": {"unknown.slot": "icons/unknown.png"},
    }), encoding="utf-8")

    report = ThemeValidator(ThemeManager(tmp_path / "themes")).validate("broken")
    issue = report.issues[0]
    payload = report.to_dict()

    assert issue.code == ThemeValidationCode.THEME_ASSET_UNKNOWN_KEY
    assert issue.field == "assets.unknown.slot"
    assert payload["report_version"] == 1
    assert payload["contract_version"] == 1
    assert payload["schema_version"] == 6
    assert payload["issues"][0]["code"] == "THEME_ASSET_UNKNOWN_KEY"


def test_invalid_json_has_stable_validation_code(tmp_path: Path) -> None:
    root = tmp_path / "themes" / "broken-json"
    root.mkdir(parents=True)
    (root / "theme.json").write_text("{broken", encoding="utf-8")

    report = ThemeValidator(ThemeManager(tmp_path / "themes")).validate_directory(root)

    assert report.is_valid is False
    assert report.issues[0].code == ThemeValidationCode.THEME_MANIFEST_INVALID_JSON


def test_schema_6_unknown_asset_is_error_but_legacy_theme_keeps_warning_compatibility(tmp_path: Path) -> None:
    strict = tmp_path / "themes" / "strict"
    strict.mkdir(parents=True)
    (strict / "theme.json").write_text(json.dumps({"schema_version": 6, "id": "strict", "assets": {"unknown.slot": "x.png"}}), encoding="utf-8")
    legacy = tmp_path / "themes" / "legacy"
    legacy.mkdir(parents=True)
    (legacy / "theme.json").write_text(json.dumps({"schema_version": 1, "id": "legacy", "assets": {"unknown.slot": "x.png"}}), encoding="utf-8")

    validator = ThemeValidator(ThemeManager(tmp_path / "themes"))

    assert validator.validate("strict").issues[0].severity == "error"
    assert validator.validate("legacy").issues[0].severity == "warning"


def test_palette_validation_uses_stable_codes(tmp_path: Path) -> None:
    root = tmp_path / "themes" / "palette"
    root.mkdir(parents=True)
    (root / "theme.json").write_text(json.dumps({
        "schema_version": 6,
        "id": "palette",
        "assets": {},
        "palette": {"primary": "not-a-color"},
        "accent_assets": ["missing.slot"],
    }), encoding="utf-8")

    report = ThemeValidator(ThemeManager(tmp_path / "themes")).validate_directory(root)
    codes = {issue.code for issue in report.issues}

    assert ThemeValidationCode.THEME_PALETTE_INVALID in codes
    assert ThemeValidationCode.THEME_ACCENT_ASSET_INVALID in codes
