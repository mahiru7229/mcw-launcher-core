from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.core.theme.theme_contract import (
    ASSET_CATALOG_FILENAME,
    CONTRACT_FILENAME,
    SCHEMA_FILENAME,
    SUPPORTED_THEME_SCHEMA_VERSIONS,
    THEME_ASSET_CATALOG_VERSION,
    THEME_PACKAGE_FORMAT_VERSION,
    THEME_RUNTIME_CONTRACT_VERSION,
    THEME_SCHEMA_VERSION,
    THEME_VALIDATION_CODES_V1,
    THEME_PACKAGE_ERROR_CODES_V1,
    THEME_VALIDATION_REPORT_VERSION,
    build_theme_asset_catalog_v1,
    build_theme_runtime_contract_v1,
    build_theme_schema_v6,
    pretty_json_text,
    write_contract_documents,
)
from src.core.theme.theme_catalog import THEME_ASSET_BY_KEY
from src.core.theme.theme_manager import ThemeManager
from src.core.theme.theme_validation import ThemeValidationCode


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = PROJECT_ROOT / "docs" / "schema"


def test_theme_runtime_contract_versions_are_frozen() -> None:
    assert THEME_RUNTIME_CONTRACT_VERSION == 1
    assert THEME_SCHEMA_VERSION == 6
    assert THEME_ASSET_CATALOG_VERSION == 1
    assert THEME_PACKAGE_FORMAT_VERSION == 1
    assert THEME_VALIDATION_REPORT_VERSION == 1
    assert SUPPORTED_THEME_SCHEMA_VERSIONS == frozenset({1, 2, 3, 4, 5, 6})
    assert ThemeManager.LATEST_SCHEMA_VERSION == THEME_SCHEMA_VERSION
    assert ThemeManager.SUPPORTED_SCHEMA_VERSIONS == SUPPORTED_THEME_SCHEMA_VERSIONS


def test_shipped_contract_documents_match_runtime_generators() -> None:
    expected = {
        SCHEMA_FILENAME: build_theme_schema_v6(),
        ASSET_CATALOG_FILENAME: build_theme_asset_catalog_v1(),
        CONTRACT_FILENAME: build_theme_runtime_contract_v1(),
    }
    for filename, payload in expected.items():
        path = SCHEMA_ROOT / filename
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_contract_writer_uses_lf_line_endings(tmp_path: Path) -> None:
    paths = write_contract_documents(tmp_path)
    for path in paths:
        payload = path.read_bytes()
        assert b"\r\n" not in payload
        assert payload.endswith(b"\n")


def test_contract_document_hashes_match_shipped_files() -> None:
    contract = json.loads((SCHEMA_ROOT / CONTRACT_FILENAME).read_text(encoding="utf-8"))
    for filename, expected in contract["sha256"].items():
        actual = hashlib.sha256((SCHEMA_ROOT / filename).read_bytes()).hexdigest()
        assert actual == expected


def test_asset_catalog_is_complete_and_machine_readable() -> None:
    catalog = build_theme_asset_catalog_v1()
    assert set(catalog["assets"]) == set(THEME_ASSET_BY_KEY)
    for key, item in catalog["assets"].items():
        spec = THEME_ASSET_BY_KEY[key]
        assert item["type"] == "png"
        assert item["recommended_size"] == {"width": spec.width, "height": spec.height}
        assert item["default_relative_path"] == spec.relative_path


def test_schema_6_declares_known_asset_keys_and_runtime_limits() -> None:
    schema = build_theme_schema_v6()
    assert schema["properties"]["schema_version"] == {"const": 6}
    assert set(schema["properties"]["assets"]["propertyNames"]["enum"]) == set(THEME_ASSET_BY_KEY)
    assert schema["$defs"]["animation"]["properties"]["frame_count"]["maximum"] == ThemeManager.MAX_ANIMATION_FRAMES
    assert "palette" in schema["properties"]
    assert "accent_assets" in schema["properties"]
    assert set(schema["$defs"]["palette"]["properties"]) == {"primary", "primary_hover", "primary_pressed", "primary_text", "focus", "selection", "selection_text", "link", "success", "warning", "error", "text_primary", "text_muted", "text_disabled", "text_inverse"}
    assert pretty_json_text(schema).endswith("\n")


def test_theme_core_contract_does_not_import_qt() -> None:
    core_root = PROJECT_ROOT / "src" / "core" / "theme"
    for path in core_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "PySide6" not in text, path
        assert "src.gui" not in text, path


def test_contract_publishes_stable_validation_and_package_codes() -> None:
    validation_constants = {
        value for name, value in vars(ThemeValidationCode).items()
        if name.startswith("THEME_") and isinstance(value, str)
    }
    assert validation_constants == set(THEME_VALIDATION_CODES_V1)
    contract = build_theme_runtime_contract_v1()
    assert set(contract["validation_codes"]) == validation_constants
    assert set(contract["package_error_codes"]) == set(THEME_PACKAGE_ERROR_CODES_V1)
