from __future__ import annotations

import json
from pathlib import Path
import struct
import zlib

from src.core.theme.theme_manager import ThemeManager


def write_png(path: Path, width: int = 4, height: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = b"".join(b"\x00" + (b"\x00\x00\x00\x00" * width) for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    path.write_bytes(signature + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def write_manifest(root: Path, assets: dict[str, str], text_assets: dict[str, str] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "id": root.name, "name": "Test Theme", "author": "Test", "assets": assets}
    if text_assets is not None:
        payload["text_assets"] = text_assets
    (root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")


def test_valid_png_asset_is_resolved(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {"background.window": "backgrounds/window.png"})
    write_png(theme_root / "backgrounds" / "window.png", 1600, 900)

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.theme_id == "test-theme"
    assert manager.resolve_asset("background.window") == (theme_root / "backgrounds" / "window.png").resolve()


def test_missing_or_invalid_png_falls_back_without_crashing(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {"background.window": "backgrounds/missing.png", "logo.main": "logos/broken.png"})
    broken = theme_root / "logos" / "broken.png"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("not a png", encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.theme_id == "test-theme"
    assert selected.issues
    assert manager.resolve_asset("background.window") is None
    assert manager.resolve_asset("logo.main") is None


def test_unsafe_theme_asset_path_is_ignored(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {"background.window": "../outside.png"})

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.theme_id == "test-theme"
    assert "background.window" not in selected.assets
    assert manager.resolve_asset("background.window") is None


def test_invalid_theme_manifest_does_not_break_catalog(tmp_path: Path) -> None:
    invalid = tmp_path / "themes" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "theme.json").write_text("{broken", encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")

    assert [theme.theme_id for theme in manager.available_themes()] == [ThemeManager.FALLBACK_THEME_ID]
    assert manager.select("missing").theme_id == ThemeManager.FALLBACK_THEME_ID


def test_static_text_role_resolves_only_when_mapped_png_is_valid(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {"button.launch": "controls/launch.png"}, {"control.launch": "button.launch"})
    write_png(theme_root / "controls" / "launch.png", 461, 133)

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.text_assets == {"control.launch": "button.launch"}
    assert manager.resolve_text_asset("control.launch") == (theme_root / "controls" / "launch.png").resolve()


def test_static_text_role_falls_back_when_png_is_missing(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {"button.launch": "controls/missing.png"}, {"control.launch": "button.launch"})

    manager = ThemeManager(tmp_path / "themes")
    manager.select("test-theme")

    assert manager.resolve_text_asset("control.launch") is None


def test_unknown_static_text_asset_key_is_ignored(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    write_manifest(theme_root, {}, {"control.launch": "button.unknown"})

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.text_assets == {}
    assert any("Unknown text asset key" in issue for issue in selected.issues)


def test_cancel_artwork_falls_back_to_default_theme(tmp_path: Path) -> None:
    default_root = tmp_path / "themes" / ThemeManager.DEFAULT_THEME_ID
    write_manifest(default_root, {"button.cancel": "controls/cancel.png"}, {"control.cancel": "button.cancel"})
    write_png(default_root / "controls" / "cancel.png", 461, 133)

    custom_root = tmp_path / "themes" / "custom"
    write_manifest(custom_root, {"button.launch": "controls/launch.png"}, {"control.launch": "button.launch"})
    write_png(custom_root / "controls" / "launch.png", 461, 133)

    manager = ThemeManager(tmp_path / "themes")
    manager.select("custom")

    assert manager.resolve_asset("button.cancel") is None
    assert manager.resolve_asset("button.cancel", fallback_to_default=True) == (default_root / "controls" / "cancel.png").resolve()
    assert manager.resolve_text_asset("control.cancel", fallback_to_default=True) == (default_root / "controls" / "cancel.png").resolve()


def test_valid_spritesheet_animation_is_resolved(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    theme_root.mkdir(parents=True)
    payload = {
        "schema_version": 2,
        "id": "test-theme",
        "name": "Animated Theme",
        "author": "Test",
        "assets": {"progress.chunk": "controls/progress/chunk.png"},
        "animations": {
            "progress.chunk": {
                "type": "spritesheet",
                "path": "animations/progress.png",
                "fallback_asset": "progress.chunk",
                "frame_size": [8, 8],
                "frame_count": 4,
                "columns": 4,
                "frame_duration_ms": 80,
                "loop": True,
                "render_mode": "tile_x",
                "filtering": "nearest",
            }
        },
    }
    (theme_root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")
    write_png(theme_root / "controls/progress/chunk.png", 8, 8)
    write_png(theme_root / "animations/progress.png", 32, 8)

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")
    animation = manager.resolve_animation("progress.chunk")

    assert animation is not None
    assert animation.path == (theme_root / "animations/progress.png").resolve()
    assert animation.definition.frame_count == 4
    assert animation.definition.frame_width == 8
    assert animation.definition.render_mode == "tile_x"
    assert manager.resolve_animation_fallback("progress.chunk") == (theme_root / "controls/progress/chunk.png").resolve()
    assert {"animated_assets", "sprite_sheets"}.issubset(selected.capabilities)


def test_animation_rejects_unsafe_path_without_breaking_theme(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    theme_root.mkdir(parents=True)
    payload = {
        "schema_version": 2,
        "id": "test-theme",
        "assets": {},
        "animations": {
            "progress.chunk": {
                "type": "spritesheet",
                "path": "../outside.png",
                "frame_size": [8, 8],
                "frame_count": 2,
                "columns": 2,
                "frame_duration_ms": 80,
            }
        },
    }
    (theme_root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.theme_id == "test-theme"
    assert selected.animations == {}
    assert any("escapes its theme directory" in issue for issue in selected.issues)
    assert manager.resolve_animation("progress.chunk", fallback_to_default=False) is None


def test_animation_rejects_sprite_sheet_that_is_too_small(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    theme_root.mkdir(parents=True)
    payload = {
        "schema_version": 2,
        "id": "test-theme",
        "assets": {},
        "animations": {
            "progress.chunk": {
                "type": "spritesheet",
                "path": "animations/progress.png",
                "frame_size": [8, 8],
                "frame_count": 4,
                "columns": 4,
                "frame_duration_ms": 80,
            }
        },
    }
    (theme_root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")
    write_png(theme_root / "animations/progress.png", 16, 8)

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert any("sprite sheet is too small" in issue for issue in selected.issues)
    assert manager.resolve_animation("progress.chunk", fallback_to_default=False) is None


def test_missing_custom_animation_falls_back_to_default_theme(tmp_path: Path) -> None:
    default_root = tmp_path / "themes" / ThemeManager.DEFAULT_THEME_ID
    default_root.mkdir(parents=True)
    default_payload = {
        "schema_version": 2,
        "id": ThemeManager.DEFAULT_THEME_ID,
        "assets": {},
        "animations": {
            "progress.chunk": {
                "type": "spritesheet",
                "path": "animations/progress.png",
                "frame_size": [8, 8],
                "frame_count": 2,
                "columns": 2,
                "frame_duration_ms": 80,
            }
        },
    }
    (default_root / "theme.json").write_text(json.dumps(default_payload), encoding="utf-8")
    write_png(default_root / "animations/progress.png", 16, 8)

    custom_root = tmp_path / "themes" / "custom"
    write_manifest(custom_root, {})

    manager = ThemeManager(tmp_path / "themes")
    manager.select("custom")
    animation = manager.resolve_animation("progress.chunk")

    assert animation is not None
    assert animation.theme_id == ThemeManager.DEFAULT_THEME_ID
    assert animation.path == (default_root / "animations/progress.png").resolve()


def test_unsupported_animation_type_is_ignored(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "test-theme"
    theme_root.mkdir(parents=True)
    payload = {
        "schema_version": 2,
        "id": "test-theme",
        "assets": {},
        "animations": {
            "progress.chunk": {
                "type": "python",
                "path": "animation.py",
                "frame_size": [8, 8],
                "frame_count": 2,
                "columns": 2,
                "frame_duration_ms": 80,
            }
        },
    }
    (theme_root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("test-theme")

    assert selected.animations == {}
    assert any("unsupported type" in issue for issue in selected.issues)


def write_font(path: Path, signature: bytes = b"\x00\x01\x00\x00", payload_size: int = 64) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(signature + (b"\x00" * max(0, payload_size - len(signature))))


def test_valid_custom_font_is_resolved(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "font-theme"
    theme_root.mkdir(parents=True)
    payload = {
        "schema_version": 3,
        "id": "font-theme",
        "name": "Font Theme",
        "assets": {},
        "font": {
            "files": ["fonts/ui-regular.ttf", "fonts/ui-bold.otf"],
            "family": "MCW Pixel",
            "point_size": 11,
            "weight": 500,
            "italic": False,
            "letter_spacing": 1.0,
            "fallback_families": ["Segoe UI", "Arial"],
        },
    }
    (theme_root / "theme.json").write_text(json.dumps(payload), encoding="utf-8")
    write_font(theme_root / "fonts/ui-regular.ttf")
    write_font(theme_root / "fonts/ui-bold.otf", signature=b"OTTO")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("font-theme")
    resolved = manager.resolve_font()

    assert resolved is not None
    assert resolved.theme_id == "font-theme"
    assert resolved.paths == (
        (theme_root / "fonts/ui-regular.ttf").resolve(),
        (theme_root / "fonts/ui-bold.otf").resolve(),
    )
    assert resolved.definition.family == "MCW Pixel"
    assert resolved.definition.point_size == 11
    assert resolved.definition.weight == 500
    assert resolved.definition.letter_spacing == 1.0
    assert resolved.definition.fallback_families == ("Segoe UI", "Arial")
    assert "custom_font" in selected.capabilities
    assert manager.font_status()


def test_theme_font_rejects_path_traversal_without_breaking_theme(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "font-theme"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 3,
        "id": "font-theme",
        "assets": {},
        "font": {"path": "../outside.ttf"},
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("font-theme")

    assert selected.theme_id == "font-theme"
    assert selected.font is None
    assert any("escapes its theme directory" in issue for issue in selected.issues)
    assert manager.resolve_font(fallback_to_default=False) is None


def test_invalid_font_file_falls_back_safely(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "font-theme"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 3,
        "id": "font-theme",
        "assets": {},
        "font": {"path": "fonts/ui.ttf"},
    }), encoding="utf-8")
    write_font(theme_root / "fonts/ui.ttf", signature=b"NOPE")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("font-theme")

    assert selected.font is not None
    assert any("Invalid TTF/OTF theme font" in issue for issue in selected.issues)
    assert manager.resolve_font(fallback_to_default=False) is None
    assert not manager.font_status()


def test_missing_custom_font_falls_back_to_default_theme(tmp_path: Path) -> None:
    default_root = tmp_path / "themes" / ThemeManager.DEFAULT_THEME_ID
    default_root.mkdir(parents=True)
    (default_root / "theme.json").write_text(json.dumps({
        "schema_version": 3,
        "id": ThemeManager.DEFAULT_THEME_ID,
        "assets": {},
        "font": {"path": "fonts/default.ttf", "family": "Default Pixel"},
    }), encoding="utf-8")
    write_font(default_root / "fonts/default.ttf")

    custom_root = tmp_path / "themes" / "custom"
    write_manifest(custom_root, {})

    manager = ThemeManager(tmp_path / "themes")
    manager.select("custom")
    resolved = manager.resolve_font()

    assert resolved is not None
    assert resolved.theme_id == ThemeManager.DEFAULT_THEME_ID
    assert resolved.paths == ((default_root / "fonts/default.ttf").resolve(),)


def test_valid_theme_motion_configuration_is_loaded(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "motion-theme"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 4,
        "id": "motion-theme",
        "assets": {},
        "motion": {
            "page": {"type": "fade_slide", "duration_ms": 210, "easing": "out_cubic", "distance_px": 24},
            "button": {"hover_duration_ms": 90, "press_duration_ms": 60, "easing": "out_quad", "hover_strength": 0.1, "press_strength": 0.2},
            "dialog": {"type": "fade", "duration_ms": 150, "easing": "out_cubic"},
            "sidebar": {"duration_ms": 240, "easing": "in_out_cubic", "collapsed_width": 76},
            "launch_control": {"type": "fade", "duration_ms": 130, "easing": "out_quad"},
        },
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("motion-theme")

    assert selected.motion.page.transition_type == "fade_slide"
    assert selected.motion.page.duration_ms == 210
    assert selected.motion.page.distance_px == 24
    assert selected.motion.button.hover_strength == 0.1
    assert selected.motion.sidebar.collapsed_width == 76
    assert selected.motion.launch_control.duration_ms == 130
    assert "motion_configuration" in selected.capabilities


def test_invalid_theme_motion_falls_back_without_breaking_theme(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "motion-theme"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 4,
        "id": "motion-theme",
        "assets": {},
        "motion": {
            "page": {"type": "teleport", "duration_ms": 99999},
        },
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("motion-theme")

    assert selected.theme_id == "motion-theme"
    assert selected.motion.page.transition_type == "fade_slide"
    assert selected.issues
    assert any("motion page.type" in issue for issue in selected.issues)


def test_schema_five_loads_toast_and_performance_motion(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "motion-five"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 5,
        "id": "motion-five",
        "assets": {},
        "motion": {
            "toast": {
                "type": "slide_fade",
                "duration_ms": 190,
                "visible_duration_ms": 4200,
                "easing": "out_cubic",
                "distance_px": 28,
                "max_visible": 4,
            },
            "performance": {
                "full_fps": 75,
                "reduced_fps": 25,
                "pause_when_hidden": True,
            },
        },
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("motion-five")

    assert selected.motion.toast.transition_type == "slide_fade"
    assert selected.motion.toast.visible_duration_ms == 4200
    assert selected.motion.toast.max_visible == 4
    assert selected.motion.performance.full_fps == 75
    assert selected.motion.performance.reduced_fps == 25
    assert selected.motion.performance.pause_when_hidden


def test_schema_five_rejects_invalid_performance_without_breaking_theme(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "motion-five"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 5,
        "id": "motion-five",
        "assets": {},
        "motion": {
            "performance": {
                "full_fps": 30,
                "reduced_fps": 60,
                "pause_when_hidden": True,
            },
        },
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("motion-five")

    assert selected.theme_id == "motion-five"
    assert selected.motion.performance.full_fps == 60
    assert selected.motion.performance.reduced_fps == 30
    assert any("reduced_fps must not exceed full_fps" in issue for issue in selected.issues)


def test_bundled_default_theme_has_no_manifest_issues() -> None:
    theme_root = Path(__file__).resolve().parents[3] / "themes"
    manager = ThemeManager(theme_root)
    selected = manager.select(ThemeManager.DEFAULT_THEME_ID)

    assert selected.theme_id == ThemeManager.DEFAULT_THEME_ID
    assert selected.issues == ()


def test_custom_stylesheet_is_loaded_for_schema_six(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "styled"
    theme_root.mkdir(parents=True)
    (theme_root / "styles.qss").write_text("QPushButton { padding: 8px; }", encoding="utf-8")
    (theme_root / "theme.json").write_text(json.dumps({"schema_version": 6, "id": "styled", "stylesheet": "styles.qss", "assets": {}}), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("styled")

    assert selected.stylesheet == "styles.qss"
    assert manager.resolve_stylesheet() == "QPushButton { padding: 8px; }"
    assert "custom_stylesheet" in selected.capabilities


def test_custom_stylesheet_rejects_external_urls(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "styled"
    theme_root.mkdir(parents=True)
    (theme_root / "styles.qss").write_text('QWidget { image: url("https://example.invalid/a.png"); }', encoding="utf-8")
    (theme_root / "theme.json").write_text(json.dumps({"schema_version": 6, "id": "styled", "stylesheet": "styles.qss", "assets": {}}), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("styled")

    assert selected.stylesheet is None
    assert any("url()" in issue for issue in selected.issues)
    assert manager.resolve_stylesheet() == ""


def test_schema_6_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "strict-theme"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 6,
        "id": "strict-theme",
        "assets": {},
        "unknown_runtime_field": True,
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")

    assert manager.select("strict-theme").theme_id == ThemeManager.FALLBACK_THEME_ID


def test_schema_6_requires_normalized_theme_id_but_legacy_schema_remains_compatible(tmp_path: Path) -> None:
    strict_root = tmp_path / "themes" / "strict"
    strict_root.mkdir(parents=True)
    (strict_root / "theme.json").write_text(json.dumps({"schema_version": 6, "id": "Not Normalized", "assets": {}}), encoding="utf-8")
    legacy_root = tmp_path / "themes" / "legacy"
    legacy_root.mkdir(parents=True)
    (legacy_root / "theme.json").write_text(json.dumps({"schema_version": 1, "id": "Legacy Theme", "assets": {}}), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")

    assert manager.select("Not Normalized").theme_id == ThemeManager.FALLBACK_THEME_ID
    assert manager.select("Legacy Theme").theme_id == "Legacy Theme"


def test_schema_six_loads_palette_and_accent_assets(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "accented"
    theme_root.mkdir(parents=True)
    write_png(theme_root / "controls" / "primary.png")
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 6,
        "id": "accented",
        "assets": {"button.primary": "controls/primary.png"},
        "palette": {
            "primary": "#3366cc",
            "primary_hover": "#4477dd",
            "primary_pressed": "#224499",
        },
        "accent_assets": ["button.primary"],
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("accented")

    assert selected.palette.primary == "#3366cc"
    assert selected.palette.primary_hover == "#4477dd"
    assert selected.palette.primary_text == "#ffffff"
    assert selected.accent_assets == frozenset({"button.primary"})
    assert "theme_palette" in selected.capabilities
    assert "accent_tint" in selected.capabilities
    assert selected.issues == ()


def test_invalid_palette_and_unknown_accent_asset_are_reported_without_crashing(tmp_path: Path) -> None:
    theme_root = tmp_path / "themes" / "accented"
    theme_root.mkdir(parents=True)
    (theme_root / "theme.json").write_text(json.dumps({
        "schema_version": 6,
        "id": "accented",
        "assets": {},
        "palette": {"primary": "blue"},
        "accent_assets": ["button.missing"],
    }), encoding="utf-8")

    manager = ThemeManager(tmp_path / "themes")
    selected = manager.select("accented")

    assert selected.theme_id == "accented"
    assert selected.palette.primary == "#63984a"
    assert selected.accent_assets == frozenset()
    assert any("#RRGGBB" in issue for issue in selected.issues)
    assert any("Unknown accent asset key" in issue for issue in selected.issues)
