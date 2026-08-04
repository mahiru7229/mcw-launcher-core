from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from src.core.theme.theme_catalog import THEME_ASSET_SPECS
from src.core.theme.theme_palette import HEX_COLOR_PATTERN_TEXT, PALETTE_FIELDS

THEME_RUNTIME_CONTRACT_VERSION = 1
THEME_SCHEMA_VERSION = 6
THEME_ASSET_CATALOG_VERSION = 1
THEME_PACKAGE_FORMAT_VERSION = 1
THEME_VALIDATION_REPORT_VERSION = 1
SUPPORTED_THEME_SCHEMA_VERSIONS = frozenset(range(1, THEME_SCHEMA_VERSION + 1))

THEME_ID_PATTERN_TEXT = r"^[a-z0-9][a-z0-9._-]{0,63}$"
THEME_ID_PATTERN = re.compile(THEME_ID_PATTERN_TEXT)
ANIMATION_KEY_PATTERN_TEXT = r"^[a-z0-9][a-z0-9._-]{0,127}$"
ANIMATION_KEY_PATTERN = re.compile(ANIMATION_KEY_PATTERN_TEXT)
STATIC_TEXT_ROLE_PATTERN_TEXT = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"

MAX_MANIFEST_BYTES = 512 * 1024
MAX_STYLESHEET_BYTES = 512 * 1024
MAX_ANIMATION_FRAMES = 256
MIN_FRAME_DURATION_MS = 16
MAX_FRAME_DURATION_MS = 10_000
MAX_FONT_FILES = 8
MAX_FONT_FILE_BYTES = 16 * 1024 * 1024
MAX_FONT_TOTAL_BYTES = 32 * 1024 * 1024
MAX_THEME_ARCHIVE_FILES = 2048
MAX_THEME_ARCHIVE_BYTES = 128 * 1024 * 1024

ANIMATION_RENDER_MODES = frozenset({"tile_x", "stretch", "contain"})
ANIMATION_FILTERING_MODES = frozenset({"nearest", "smooth"})
FONT_EXTENSIONS = frozenset({".ttf", ".otf"})
FONT_WEIGHTS = frozenset({100, 200, 300, 400, 500, 600, 700, 800, 900})
MOTION_EASINGS = frozenset({"linear", "in_quad", "out_quad", "in_out_quad", "in_cubic", "out_cubic", "in_out_cubic", "out_back"})
PAGE_TRANSITIONS = frozenset({"none", "fade", "slide_left", "slide_right", "fade_slide"})
DIALOG_TRANSITIONS = frozenset({"none", "fade"})
LAUNCH_TRANSITIONS = frozenset({"none", "fade"})
TOAST_TRANSITIONS = frozenset({"none", "fade", "slide", "slide_fade"})


THEME_VALIDATION_CODES_V1: dict[str, dict[str, str]] = {
    "THEME_NOT_INSTALLED": {"category": "manifest", "default_severity": "error"},
    "THEME_MANIFEST_MISSING": {"category": "manifest", "default_severity": "error"},
    "THEME_MANIFEST_INVALID_JSON": {"category": "manifest", "default_severity": "error"},
    "THEME_MANIFEST_INVALID_ROOT": {"category": "manifest", "default_severity": "error"},
    "THEME_SCHEMA_INVALID": {"category": "manifest", "default_severity": "error"},
    "THEME_SCHEMA_UNSUPPORTED": {"category": "manifest", "default_severity": "error"},
    "THEME_ID_INVALID": {"category": "manifest", "default_severity": "error"},
    "THEME_ASSET_UNKNOWN_KEY": {"category": "asset", "default_severity": "warning"},
    "THEME_ASSET_MISSING_FILE": {"category": "asset", "default_severity": "error"},
    "THEME_ASSET_INVALID_PNG": {"category": "asset", "default_severity": "error"},
    "THEME_ASSET_UNSAFE_PATH": {"category": "security", "default_severity": "error"},
    "THEME_TEXT_ASSET_INVALID": {"category": "asset", "default_severity": "warning"},
    "THEME_ANIMATION_INVALID": {"category": "animation", "default_severity": "error"},
    "THEME_ANIMATION_SHEET_TOO_SMALL": {"category": "animation", "default_severity": "error"},
    "THEME_FONT_INVALID": {"category": "font", "default_severity": "error"},
    "THEME_MOTION_INVALID": {"category": "motion", "default_severity": "error"},
    "THEME_PALETTE_INVALID": {"category": "palette", "default_severity": "error"},
    "THEME_ACCENT_ASSET_INVALID": {"category": "palette", "default_severity": "error"},
    "THEME_STYLESHEET_INVALID": {"category": "style", "default_severity": "error"},
    "THEME_CAPABILITY_INVALID": {"category": "manifest", "default_severity": "warning"},
    "THEME_SECURITY_VIOLATION": {"category": "security", "default_severity": "error"},
    "THEME_UNKNOWN_ISSUE": {"category": "asset", "default_severity": "error"},
}

THEME_PACKAGE_ERROR_CODES_V1: tuple[str, ...] = (
    "THEME_PACKAGE_NOT_FOUND",
    "THEME_PACKAGE_READ_FAILED",
    "THEME_PACKAGE_FILE_COUNT_INVALID",
    "THEME_PACKAGE_ENCRYPTED",
    "THEME_PACKAGE_SYMLINK",
    "THEME_PACKAGE_DUPLICATE_PATH",
    "THEME_PACKAGE_PATH_UNSAFE",
    "THEME_PACKAGE_DIRECTORY_DISALLOWED",
    "THEME_PACKAGE_FILE_TYPE_UNSUPPORTED",
    "THEME_PACKAGE_SIZE_LIMIT",
    "THEME_PACKAGE_ROOT_INVALID",
    "THEME_PACKAGE_MANIFEST_MISSING",
    "THEME_PACKAGE_CHECKSUM_MANIFEST_INVALID",
    "THEME_PACKAGE_CHECKSUM_ALGORITHM_UNSUPPORTED",
    "THEME_PACKAGE_CHECKSUM_PATH_UNSAFE",
    "THEME_PACKAGE_CHECKSUM_SELF_REFERENCE",
    "THEME_PACKAGE_CHECKSUM_DUPLICATE_PATH",
    "THEME_PACKAGE_CHECKSUM_FILE_MISSING",
    "THEME_PACKAGE_CHECKSUM_EXTRA_FILE",
    "THEME_PACKAGE_CHECKSUM_MISMATCH",
    "THEME_PACKAGE_FORMAT_VERSION_INVALID",
    "THEME_PACKAGE_FORMAT_VERSION_UNSUPPORTED",
    "THEME_PACKAGE_ID_MISMATCH",
)

SCHEMA_FILENAME = "theme.schema.v6.json"
ASSET_CATALOG_FILENAME = "theme-assets.v1.json"
CONTRACT_FILENAME = "theme-runtime-contract.v1.json"

# JSON Schema uses the same conservative path rules as the runtime. The runtime
# remains authoritative because JSON Schema cannot resolve filesystem paths.
_SAFE_RELATIVE_PATH_PATTERN = r"^(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[^\\\x00]+$"
_SAFE_PNG_PATH_PATTERN = _SAFE_RELATIVE_PATH_PATTERN[:-1] + r"\.png$"
_SAFE_QSS_PATH_PATTERN = _SAFE_RELATIVE_PATH_PATTERN[:-1] + r"\.qss$"
_SAFE_FONT_PATH_PATTERN = _SAFE_RELATIVE_PATH_PATTERN[:-1] + r"\.(?:ttf|otf)$"


def canonical_json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def pretty_json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _transition_schema(types: frozenset[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": sorted(types)},
            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 3000},
            "easing": {"type": "string", "enum": sorted(MOTION_EASINGS)},
            "distance_px": {"type": "integer", "minimum": 0, "maximum": 256},
        },
    }


def build_theme_schema_v6() -> dict[str, Any]:
    asset_keys = sorted(spec.key for spec in THEME_ASSET_SPECS)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://mcw-launcher.local/schema/theme.schema.v6.json",
        "title": "MCW Launcher Theme Manifest",
        "description": "Frozen theme runtime contract for MCW Launcher v0.11.x and MCW Theme Studio.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "id"],
        "properties": {
            "$schema": {"type": "string", "maxLength": 512},
            "schema_version": {"const": THEME_SCHEMA_VERSION},
            "id": {"type": "string", "pattern": THEME_ID_PATTERN_TEXT},
            "name": {"type": "string", "minLength": 1, "maxLength": 128},
            "author": {"type": "string", "minLength": 1, "maxLength": 128},
            "description": {"type": "string", "maxLength": 2048},
            "assets": {
                "type": "object",
                "propertyNames": {"enum": asset_keys},
                "additionalProperties": {"type": "string", "pattern": _SAFE_PNG_PATH_PATTERN},
                "default": {},
            },
            "text_assets": {
                "type": "object",
                "propertyNames": {"pattern": STATIC_TEXT_ROLE_PATTERN_TEXT},
                "additionalProperties": {"type": "string", "enum": asset_keys},
                "default": {},
            },
            "animations": {
                "type": "object",
                "propertyNames": {"pattern": ANIMATION_KEY_PATTERN_TEXT},
                "additionalProperties": {"$ref": "#/$defs/animation"},
                "default": {},
            },
            "font": {"$ref": "#/$defs/font"},
            "motion": {"$ref": "#/$defs/motion"},
            "palette": {"$ref": "#/$defs/palette"},
            "accent_assets": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "string", "enum": asset_keys},
                        {"type": "string", "pattern": ANIMATION_KEY_PATTERN_TEXT},
                    ]
                },
                "maxItems": MAX_ANIMATION_FRAMES + len(asset_keys),
                "uniqueItems": True,
                "default": [],
            },
            "stylesheet": {"type": "string", "pattern": _SAFE_QSS_PATH_PATTERN},
            "capabilities": {
                "oneOf": [
                    {"type": "object", "additionalProperties": {"type": "boolean"}},
                    {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 128}, "uniqueItems": True},
                ]
            },
        },
        "$defs": {
            "animation": {
                "type": "object",
                "additionalProperties": False,
                "required": ["path", "frame_size", "frame_count"],
                "properties": {
                    "type": {"const": "spritesheet", "default": "spritesheet"},
                    "path": {"type": "string", "pattern": _SAFE_PNG_PATH_PATTERN},
                    "frame_size": {
                        "type": "array",
                        "prefixItems": [
                            {"type": "integer", "minimum": 1, "maximum": 4096},
                            {"type": "integer", "minimum": 1, "maximum": 4096},
                        ],
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "frame_count": {"type": "integer", "minimum": 1, "maximum": MAX_ANIMATION_FRAMES},
                    "columns": {"type": "integer", "minimum": 1, "maximum": MAX_ANIMATION_FRAMES},
                    "frame_duration_ms": {"type": "integer", "minimum": MIN_FRAME_DURATION_MS, "maximum": MAX_FRAME_DURATION_MS, "default": 100},
                    "loop": {"type": "boolean", "default": True},
                    "render_mode": {"type": "string", "enum": sorted(ANIMATION_RENDER_MODES), "default": "tile_x"},
                    "scale_mode": {"type": "string", "enum": ["tile", *sorted(ANIMATION_RENDER_MODES)]},
                    "filtering": {"type": "string", "enum": sorted(ANIMATION_FILTERING_MODES), "default": "nearest"},
                    "fallback_asset": {"type": "string", "enum": asset_keys},
                    "fallback": {"type": "string", "enum": asset_keys},
                },
            },
            "font": {
                "type": "object",
                "additionalProperties": False,
                "anyOf": [{"required": ["path"]}, {"required": ["files"]}],
                "properties": {
                    "path": {"type": "string", "pattern": _SAFE_FONT_PATH_PATTERN},
                    "files": {
                        "type": "array",
                        "items": {"type": "string", "pattern": _SAFE_FONT_PATH_PATTERN},
                        "minItems": 1,
                        "maxItems": MAX_FONT_FILES,
                        "uniqueItems": True,
                    },
                    "family": {"type": "string", "minLength": 1, "maxLength": 128},
                    "point_size": {"type": "number", "minimum": 6, "maximum": 72, "default": 10.5},
                    "weight": {"type": "integer", "enum": sorted(FONT_WEIGHTS), "default": 400},
                    "italic": {"type": "boolean", "default": False},
                    "letter_spacing": {"type": "number", "minimum": -5, "maximum": 20, "default": 0},
                    "fallback_families": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 128},
                        "maxItems": 8,
                        "uniqueItems": True,
                    },
                },
            },
            "palette": {
                "type": "object",
                "additionalProperties": False,
                "properties": {field: {"type": "string", "pattern": HEX_COLOR_PATTERN_TEXT} for field in sorted(PALETTE_FIELDS)},
            },
            "motion": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "page": _transition_schema(PAGE_TRANSITIONS),
                    "dialog": _transition_schema(DIALOG_TRANSITIONS),
                    "launch_control": _transition_schema(LAUNCH_TRANSITIONS),
                    "button": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "hover_duration_ms": {"type": "integer", "minimum": 0, "maximum": 2000},
                            "press_duration_ms": {"type": "integer", "minimum": 0, "maximum": 2000},
                            "easing": {"type": "string", "enum": sorted(MOTION_EASINGS)},
                            "hover_strength": {"type": "number", "minimum": 0, "maximum": 1},
                            "press_strength": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                    "sidebar": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 3000},
                            "easing": {"type": "string", "enum": sorted(MOTION_EASINGS)},
                            "collapsed_width": {"type": "integer", "minimum": 56, "maximum": 160},
                        },
                    },
                    "toast": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string", "enum": sorted(TOAST_TRANSITIONS)},
                            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 3000},
                            "visible_duration_ms": {"type": "integer", "minimum": 500, "maximum": 30000},
                            "easing": {"type": "string", "enum": sorted(MOTION_EASINGS)},
                            "distance_px": {"type": "integer", "minimum": 0, "maximum": 256},
                            "max_visible": {"type": "integer", "minimum": 1, "maximum": 8},
                        },
                    },
                    "performance": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "full_fps": {"type": "integer", "minimum": 15, "maximum": 120},
                            "reduced_fps": {"type": "integer", "minimum": 10, "maximum": 60},
                            "pause_when_hidden": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    }


def build_theme_asset_catalog_v1() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "catalog_version": THEME_ASSET_CATALOG_VERSION,
        "theme_schema_version": THEME_SCHEMA_VERSION,
        "assets": {
            spec.key: {
                "type": "png",
                "default_relative_path": spec.relative_path,
                "recommended_size": {"width": spec.width, "height": spec.height},
                "category": spec.category,
                "purpose": spec.purpose,
                "required": spec.required,
                "default_theme_fallback": not spec.required,
            }
            for spec in sorted(THEME_ASSET_SPECS, key=lambda item: item.key)
        },
    }


def build_theme_runtime_contract_v1() -> dict[str, Any]:
    schema = build_theme_schema_v6()
    catalog = build_theme_asset_catalog_v1()
    return {
        "contract_version": THEME_RUNTIME_CONTRACT_VERSION,
        "theme_schema_version": THEME_SCHEMA_VERSION,
        "supported_theme_schema_versions": sorted(SUPPORTED_THEME_SCHEMA_VERSIONS),
        "asset_catalog_version": THEME_ASSET_CATALOG_VERSION,
        "package_format_version": THEME_PACKAGE_FORMAT_VERSION,
        "validation_report_version": THEME_VALIDATION_REPORT_VERSION,
        "validation_codes": THEME_VALIDATION_CODES_V1,
        "package_error_codes": list(THEME_PACKAGE_ERROR_CODES_V1),
        "schema_file": SCHEMA_FILENAME,
        "asset_catalog_file": ASSET_CATALOG_FILENAME,
        "compatibility_policy": {
            "schema_6_frozen": True,
            "existing_fields_will_not_change_meaning": True,
            "future_breaking_changes_require_new_schema_version": True,
            "new_schema_6_fields_must_be_optional": True,
            "unknown_future_schema_versions_are_rejected": True,
        },
        "sha256": {
            SCHEMA_FILENAME: hashlib.sha256(pretty_json_text(schema).encode("utf-8")).hexdigest(),
            ASSET_CATALOG_FILENAME: hashlib.sha256(pretty_json_text(catalog).encode("utf-8")).hexdigest(),
        },
    }


def _write_utf8_lf(path: Path, text: str) -> None:
    # Contract hashes are defined over UTF-8 bytes with LF line endings.
    # Explicit newline handling prevents Windows from translating ``\n``
    # into CRLF and invalidating the shipped SHA-256 values.
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_contract_documents(directory: Path) -> tuple[Path, Path, Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    schema_path = root / SCHEMA_FILENAME
    catalog_path = root / ASSET_CATALOG_FILENAME
    contract_path = root / CONTRACT_FILENAME
    _write_utf8_lf(schema_path, pretty_json_text(build_theme_schema_v6()))
    _write_utf8_lf(catalog_path, pretty_json_text(build_theme_asset_catalog_v1()))
    _write_utf8_lf(contract_path, pretty_json_text(build_theme_runtime_contract_v1()))
    return schema_path, catalog_path, contract_path
