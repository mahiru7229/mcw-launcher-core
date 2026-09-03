from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import struct
from threading import RLock
from typing import Any

from src.core.fs.paths import Paths
from src.core.theme.theme_animation import ResolvedThemeAnimation, ThemeAnimationDefinition
from src.core.theme.theme_contract import (
    ANIMATION_FILTERING_MODES,
    ANIMATION_KEY_PATTERN,
    ANIMATION_RENDER_MODES,
    DIALOG_TRANSITIONS,
    FONT_EXTENSIONS,
    FONT_WEIGHTS,
    LAUNCH_TRANSITIONS,
    MAX_ANIMATION_FRAMES,
    MAX_FONT_FILES,
    MAX_FONT_FILE_BYTES,
    MAX_FONT_TOTAL_BYTES,
    MAX_FRAME_DURATION_MS,
    MAX_MANIFEST_BYTES,
    MAX_STYLESHEET_BYTES,
    MIN_FRAME_DURATION_MS,
    MOTION_EASINGS,
    PAGE_TRANSITIONS,
    SUPPORTED_THEME_SCHEMA_VERSIONS,
    THEME_ID_PATTERN,
    THEME_SCHEMA_VERSION,
    TOAST_TRANSITIONS,
)
from src.core.theme.theme_catalog import THEME_ASSET_BY_KEY
from src.core.theme.theme_font import ResolvedThemeFont, ThemeFontDefinition
from src.core.theme.theme_motion import ButtonMotionDefinition, MotionPerformanceDefinition, MotionTransitionDefinition, SidebarMotionDefinition, ThemeMotionDefinition, ToastMotionDefinition
from src.core.theme.theme_palette import DEFAULT_THEME_PALETTE, PALETTE_FIELDS, ThemePaletteDefinition, normalize_hex_color


class ThemeError(RuntimeError):
    pass


class ThemeManifestError(ThemeError):
    pass


class ThemeAssetError(ThemeError):
    pass


@dataclass(frozen=True)
class ThemeDefinition:
    theme_id: str
    name: str
    author: str
    root: Path | None
    schema_version: int = 1
    assets: dict[str, str] = field(default_factory=dict)
    text_assets: dict[str, str] = field(default_factory=dict)
    animations: dict[str, ThemeAnimationDefinition] = field(default_factory=dict)
    font: ThemeFontDefinition | None = None
    motion: ThemeMotionDefinition = field(default_factory=ThemeMotionDefinition)
    palette: ThemePaletteDefinition = field(default_factory=ThemePaletteDefinition)
    accent_assets: frozenset[str] = frozenset()
    stylesheet: str | None = None
    capabilities: frozenset[str] = frozenset()
    issues: tuple[str, ...] = ()
    builtin_fallback: bool = False


class ThemeManager:
    DEFAULT_THEME_ID = "mcw-default"
    FALLBACK_THEME_ID = "builtin-css"
    MANIFEST_NAME = "theme.json"
    LATEST_SCHEMA_VERSION = THEME_SCHEMA_VERSION
    MAX_MANIFEST_BYTES = MAX_MANIFEST_BYTES
    MAX_STYLESHEET_BYTES = MAX_STYLESHEET_BYTES
    SUPPORTED_SCHEMA_VERSIONS = SUPPORTED_THEME_SCHEMA_VERSIONS
    MAX_ANIMATION_FRAMES = MAX_ANIMATION_FRAMES
    MIN_FRAME_DURATION_MS = MIN_FRAME_DURATION_MS
    MAX_FRAME_DURATION_MS = MAX_FRAME_DURATION_MS
    ANIMATION_KEY_PATTERN = ANIMATION_KEY_PATTERN
    ANIMATION_RENDER_MODES = ANIMATION_RENDER_MODES
    ANIMATION_FILTERING_MODES = ANIMATION_FILTERING_MODES
    FONT_EXTENSIONS = FONT_EXTENSIONS
    FONT_WEIGHTS = FONT_WEIGHTS
    MAX_FONT_FILES = MAX_FONT_FILES
    MAX_FONT_FILE_BYTES = MAX_FONT_FILE_BYTES
    MAX_FONT_TOTAL_BYTES = MAX_FONT_TOTAL_BYTES
    MOTION_EASINGS = MOTION_EASINGS
    PAGE_TRANSITIONS = PAGE_TRANSITIONS
    DIALOG_TRANSITIONS = DIALOG_TRANSITIONS
    LAUNCH_TRANSITIONS = LAUNCH_TRANSITIONS
    TOAST_TRANSITIONS = TOAST_TRANSITIONS
    SCHEMA_V6_FIELDS = frozenset({
        "$schema",
        "schema_version",
        "id",
        "name",
        "author",
        "description",
        "assets",
        "text_assets",
        "animations",
        "font",
        "motion",
        "palette",
        "accent_assets",
        "stylesheet",
        "capabilities",
    })

    def __init__(self, root: Path | None = None) -> None:
        self._uses_default_root = root is None
        self.root = Path(root) if root is not None else Paths.THEME_ROOT
        self._lock = RLock()
        self._themes: dict[str, ThemeDefinition] = {}
        self._current = self._fallback_theme()
        self.reload()

    @property
    def current(self) -> ThemeDefinition:
        with self._lock:
            return self._current

    def reload(self) -> tuple[ThemeDefinition, ...]:
        with self._lock:
            if self._uses_default_root:
                self.root = Path(Paths.THEME_ROOT)
            themes = {self.FALLBACK_THEME_ID: self._fallback_theme()}
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                directories = sorted((path for path in self.root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold())
            except OSError:
                directories = []

            for directory in directories:
                try:
                    definition = self._load_theme(directory)
                except ThemeError:
                    continue
                themes[definition.theme_id] = definition

            current_id = self._current.theme_id if self._themes else self.DEFAULT_THEME_ID
            self._themes = themes
            self._current = themes.get(current_id) or themes.get(self.DEFAULT_THEME_ID) or themes[self.FALLBACK_THEME_ID]
            return self.available_themes()

    def available_themes(self) -> tuple[ThemeDefinition, ...]:
        with self._lock:
            return tuple(sorted(self._themes.values(), key=lambda theme: (theme.builtin_fallback, theme.name.casefold())))

    def select(self, theme_id: str) -> ThemeDefinition:
        normalized = str(theme_id or "").strip()
        with self._lock:
            self._current = self._themes.get(normalized) or self._themes.get(self.DEFAULT_THEME_ID) or self._themes[self.FALLBACK_THEME_ID]
            return self._current

    def resolve_asset(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None:
        selected = theme or self.current
        resolved = self._resolve_asset_for_theme(str(key), selected)
        if resolved is not None or not fallback_to_default or selected.theme_id == self.DEFAULT_THEME_ID:
            return resolved
        fallback = self._default_theme()
        return self._resolve_asset_for_theme(str(key), fallback) if fallback is not None else None

    def resolve_text_asset(self, role: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = False) -> Path | None:
        selected = theme or self.current
        asset_key = selected.text_assets.get(str(role))
        if asset_key:
            resolved = self.resolve_asset(asset_key, selected)
            if resolved is not None:
                return resolved
        if not fallback_to_default or selected.theme_id == self.DEFAULT_THEME_ID:
            return None
        fallback = self._default_theme()
        if fallback is None:
            return None
        fallback_key = fallback.text_assets.get(str(role))
        return self.resolve_asset(fallback_key, fallback) if fallback_key else None

    def resolve_animation(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeAnimation | None:
        selected = theme or self.current
        resolved = self._resolve_animation_for_theme(str(key), selected)
        if resolved is not None or not fallback_to_default or selected.theme_id == self.DEFAULT_THEME_ID:
            return resolved
        fallback = self._default_theme()
        return self._resolve_animation_for_theme(str(key), fallback) if fallback is not None else None

    def resolve_animation_fallback(self, key: str, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> Path | None:
        selected = theme or self.current
        definition = selected.animations.get(str(key))
        if definition is not None and definition.fallback_asset:
            resolved = self.resolve_asset(definition.fallback_asset, selected)
            if resolved is not None:
                return resolved
        if not fallback_to_default or selected.theme_id == self.DEFAULT_THEME_ID:
            return None
        fallback = self._default_theme()
        if fallback is None:
            return None
        fallback_definition = fallback.animations.get(str(key))
        if fallback_definition is None or not fallback_definition.fallback_asset:
            return None
        return self.resolve_asset(fallback_definition.fallback_asset, fallback)

    def resolve_font(self, theme: ThemeDefinition | None = None, fallback_to_default: bool = True) -> ResolvedThemeFont | None:
        selected = theme or self.current
        resolved = self._resolve_font_for_theme(selected)
        if resolved is not None or not fallback_to_default or selected.theme_id == self.DEFAULT_THEME_ID:
            return resolved
        fallback = self._default_theme()
        return self._resolve_font_for_theme(fallback) if fallback is not None else None

    def resolve_palette(self, theme: ThemeDefinition | None = None) -> ThemePaletteDefinition:
        return (theme or self.current).palette

    def is_accent_asset(self, key: str, theme: ThemeDefinition | None = None) -> bool:
        return str(key) in (theme or self.current).accent_assets

    def resolve_stylesheet(self, theme: ThemeDefinition | None = None) -> str:
        selected = theme or self.current
        if selected.root is None or not selected.stylesheet:
            return ""
        try:
            path = self._safe_stylesheet_path(selected.root, selected.stylesheet)
            return self._read_stylesheet(path)
        except ThemeAssetError:
            return ""

    def _default_theme(self) -> ThemeDefinition | None:
        with self._lock:
            return self._themes.get(self.DEFAULT_THEME_ID)

    def _resolve_asset_for_theme(self, key: str, selected: ThemeDefinition) -> Path | None:
        if selected.root is None:
            return None
        relative = selected.assets.get(str(key))
        if not relative:
            return None
        try:
            candidate = self._safe_png_path(selected.root, relative)
            self._validate_png(candidate)
            return candidate
        except ThemeAssetError:
            return None

    def _resolve_animation_for_theme(self, key: str, selected: ThemeDefinition) -> ResolvedThemeAnimation | None:
        if selected.root is None:
            return None
        definition = selected.animations.get(str(key))
        if definition is None:
            return None
        try:
            candidate = self._safe_png_path(selected.root, definition.path)
            self._validate_animation_sheet(candidate, definition)
        except ThemeAssetError:
            return None
        return ResolvedThemeAnimation(definition=definition, path=candidate, theme_id=selected.theme_id)

    def _resolve_font_for_theme(self, selected: ThemeDefinition) -> ResolvedThemeFont | None:
        if selected.root is None or selected.font is None:
            return None
        paths: list[Path] = []
        total_bytes = 0
        try:
            for relative in selected.font.paths:
                candidate = self._safe_font_path(selected.root, relative)
                total_bytes += self._validate_font(candidate)
                paths.append(candidate)
            if total_bytes > self.MAX_FONT_TOTAL_BYTES:
                raise ThemeAssetError("Theme font files exceed the total size limit.")
        except ThemeAssetError:
            return None
        return ResolvedThemeFont(definition=selected.font, paths=tuple(paths), theme_id=selected.theme_id)

    def asset_status(self, theme: ThemeDefinition | None = None) -> dict[str, bool]:
        selected = theme or self.current
        return {key: self.resolve_asset(key, selected) is not None for key in THEME_ASSET_BY_KEY}

    def animation_status(self, theme: ThemeDefinition | None = None) -> dict[str, bool]:
        selected = theme or self.current
        return {key: self.resolve_animation(key, selected, fallback_to_default=False) is not None for key in selected.animations}

    def font_status(self, theme: ThemeDefinition | None = None) -> bool:
        selected = theme or self.current
        return self.resolve_font(selected, fallback_to_default=False) is not None

    def _load_theme(self, directory: Path) -> ThemeDefinition:
        manifest_path = directory / self.MANIFEST_NAME
        if not manifest_path.is_file():
            raise ThemeManifestError(f"Missing {self.MANIFEST_NAME}: {directory}")
        try:
            if manifest_path.stat().st_size > self.MAX_MANIFEST_BYTES:
                raise ThemeManifestError(f"Theme manifest is too large: {manifest_path}")
            payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ThemeManifestError(f"Unable to read theme manifest: {manifest_path}") from error
        if not isinstance(payload, dict):
            raise ThemeManifestError("Theme manifest root must be an object.")

        try:
            schema_version = int(payload.get("schema_version", 1) or 1)
        except (TypeError, ValueError) as error:
            raise ThemeManifestError("Theme schema_version must be an integer.") from error
        if schema_version not in self.SUPPORTED_SCHEMA_VERSIONS:
            raise ThemeManifestError(f"Unsupported theme schema version: {schema_version}")
        if schema_version == self.LATEST_SCHEMA_VERSION:
            self._validate_schema_v6_manifest(payload)

        theme_id = str(payload.get("id") or directory.name).strip()
        if not theme_id or theme_id in {".", ".."} or any(character in theme_id for character in "/\\:"):
            raise ThemeManifestError("Theme ID is invalid.")
        if schema_version == self.LATEST_SCHEMA_VERSION and not THEME_ID_PATTERN.fullmatch(theme_id):
            raise ThemeManifestError("Theme ID is invalid for schema 6.")
        name = str(payload.get("name") or theme_id).strip()
        author = str(payload.get("author") or "Unknown").strip()
        raw_assets = payload.get("assets", {})
        if not isinstance(raw_assets, dict):
            raise ThemeManifestError("Theme assets must be an object.")
        raw_text_assets = payload.get("text_assets", {})
        if not isinstance(raw_text_assets, dict):
            raise ThemeManifestError("Theme text_assets must be an object.")
        raw_animations = payload.get("animations", {})
        if not isinstance(raw_animations, dict):
            raise ThemeManifestError("Theme animations must be an object.")
        raw_font = payload.get("font")
        raw_motion = payload.get("motion")
        raw_palette = payload.get("palette")
        raw_accent_assets = payload.get("accent_assets", ())
        raw_stylesheet = payload.get("stylesheet")
        if raw_font is not None and not isinstance(raw_font, dict):
            raise ThemeManifestError("Theme font must be an object.")
        if raw_motion is not None and not isinstance(raw_motion, dict):
            raise ThemeManifestError("Theme motion must be an object.")
        if raw_palette is not None and not isinstance(raw_palette, dict):
            raise ThemeManifestError("Theme palette must be an object.")
        if not isinstance(raw_accent_assets, (list, tuple)):
            raise ThemeManifestError("Theme accent_assets must be an array.")
        if raw_stylesheet is not None and not isinstance(raw_stylesheet, str):
            raise ThemeManifestError("Theme stylesheet must be a string path.")

        assets: dict[str, str] = {}
        text_assets: dict[str, str] = {}
        animations: dict[str, ThemeAnimationDefinition] = {}
        font: ThemeFontDefinition | None = None
        motion = ThemeMotionDefinition()
        palette = DEFAULT_THEME_PALETTE
        accent_assets: set[str] = set()
        stylesheet: str | None = None
        issues: list[str] = []
        for key, value in raw_assets.items():
            normalized_key = str(key).strip()
            relative = str(value).strip()
            if normalized_key not in THEME_ASSET_BY_KEY:
                issues.append(f"Unknown asset key: {normalized_key}")
                continue
            try:
                candidate = self._safe_png_path(directory, relative)
            except ThemeAssetError as error:
                issues.append(str(error))
                continue
            assets[normalized_key] = candidate.relative_to(directory.resolve()).as_posix()
            if candidate.is_file():
                try:
                    self._validate_png(candidate)
                except ThemeAssetError as error:
                    issues.append(str(error))

        for role, asset_key in raw_text_assets.items():
            normalized_role = str(role).strip()
            normalized_asset_key = str(asset_key).strip()
            if not normalized_role or any(character in normalized_role for character in "/\\:"):
                issues.append(f"Invalid static text role: {normalized_role!r}")
                continue
            if normalized_asset_key not in THEME_ASSET_BY_KEY:
                issues.append(f"Unknown text asset key for {normalized_role}: {normalized_asset_key}")
                continue
            text_assets[normalized_role] = normalized_asset_key

        for key, value in raw_animations.items():
            try:
                definition = self._parse_animation(directory, key, value)
            except ThemeAssetError as error:
                issues.append(str(error))
                continue
            animations[definition.key] = definition
            candidate = directory.resolve() / definition.path
            if candidate.is_file():
                try:
                    self._validate_animation_sheet(candidate, definition)
                except ThemeAssetError as error:
                    issues.append(str(error))

        if raw_font is not None:
            try:
                font = self._parse_font(directory, raw_font)
            except ThemeAssetError as error:
                issues.append(str(error))
            else:
                total_bytes = 0
                for relative in font.paths:
                    candidate = directory.resolve() / relative
                    if not candidate.is_file():
                        issues.append(f"Theme font file is missing: {candidate}")
                        continue
                    try:
                        total_bytes += self._validate_font(candidate)
                    except ThemeAssetError as error:
                        issues.append(str(error))
                if total_bytes > self.MAX_FONT_TOTAL_BYTES:
                    issues.append(
                        f"Theme font files exceed the {self.MAX_FONT_TOTAL_BYTES // (1024 * 1024)} MiB total limit."
                    )

        if raw_motion is not None:
            try:
                motion = self._parse_motion(raw_motion)
            except ThemeAssetError as error:
                issues.append(str(error))

        if raw_palette is not None:
            try:
                palette = self._parse_palette(raw_palette)
            except ThemeAssetError as error:
                issues.append(str(error))

        for raw_key in raw_accent_assets:
            normalized_key = str(raw_key).strip()
            if normalized_key not in assets and normalized_key not in animations:
                issues.append(f"Unknown accent asset key: {normalized_key}")
                continue
            accent_assets.add(normalized_key)

        if raw_stylesheet is not None:
            try:
                stylesheet_path = self._safe_stylesheet_path(directory, raw_stylesheet)
                self._read_stylesheet(stylesheet_path)
                stylesheet = stylesheet_path.relative_to(directory.resolve()).as_posix()
            except ThemeAssetError as error:
                issues.append(str(error))

        capabilities = self._parse_capabilities(payload.get("capabilities", {}), issues)
        if animations:
            capabilities = frozenset({*capabilities, "animated_assets", "sprite_sheets"})
        if font is not None:
            capabilities = frozenset({*capabilities, "custom_font"})
        if raw_motion is not None:
            capabilities = frozenset({*capabilities, "motion_configuration"})
        if raw_palette is not None:
            capabilities = frozenset({*capabilities, "theme_palette"})
        if accent_assets:
            capabilities = frozenset({*capabilities, "accent_tint"})
        if stylesheet is not None:
            capabilities = frozenset({*capabilities, "custom_stylesheet"})

        return ThemeDefinition(
            theme_id=theme_id,
            name=name,
            author=author,
            root=directory.resolve(),
            schema_version=schema_version,
            assets=assets,
            text_assets=text_assets,
            animations=animations,
            font=font,
            motion=motion,
            palette=palette,
            accent_assets=frozenset(accent_assets),
            stylesheet=stylesheet,
            capabilities=capabilities,
            issues=tuple(issues),
        )


    @classmethod
    def _validate_schema_v6_manifest(cls, payload: dict[str, object]) -> None:
        unknown = sorted(str(key) for key in payload if str(key) not in cls.SCHEMA_V6_FIELDS)
        if unknown:
            raise ThemeManifestError(f"Theme schema 6 contains unknown top-level field: {unknown[0]}")
        if "id" not in payload:
            raise ThemeManifestError("Theme schema 6 requires id.")
        for field_name in ("id", "name", "author", "description", "$schema"):
            value = payload.get(field_name)
            if value is not None and not isinstance(value, str):
                raise ThemeManifestError(f"Theme schema 6 field {field_name} must be a string.")
        for field_name, maximum in (("name", 128), ("author", 128), ("description", 2048), ("$schema", 512)):
            value = payload.get(field_name)
            if isinstance(value, str) and len(value) > maximum:
                raise ThemeManifestError(f"Theme schema 6 field {field_name} exceeds {maximum} characters.")
        for field_name in ("name", "author"):
            value = payload.get(field_name)
            if isinstance(value, str) and not value.strip():
                raise ThemeManifestError(f"Theme schema 6 field {field_name} must not be empty.")
        for object_name in ("assets", "text_assets", "animations", "font", "motion", "palette"):
            value = payload.get(object_name)
            if value is not None and not isinstance(value, dict):
                raise ThemeManifestError(f"Theme {object_name} must be an object.")
        accent_assets = payload.get("accent_assets")
        if accent_assets is not None and (not isinstance(accent_assets, list) or any(not isinstance(item, str) for item in accent_assets)):
            raise ThemeManifestError("Theme accent_assets must be an array of strings.")
        if isinstance(accent_assets, list) and len(accent_assets) != len(set(accent_assets)):
            raise ThemeManifestError("Theme accent_assets must not contain duplicate keys.")
        stylesheet = payload.get("stylesheet")
        if stylesheet is not None and not isinstance(stylesheet, str):
            raise ThemeManifestError("Theme stylesheet must be a string path.")
        capabilities = payload.get("capabilities")
        if capabilities is not None and not isinstance(capabilities, (dict, list, tuple)):
            raise ThemeManifestError("Theme capabilities must be an object or list.")
        assets = payload.get("assets")
        if isinstance(assets, dict) and any(not isinstance(key, str) or not isinstance(value, str) for key, value in assets.items()):
            raise ThemeManifestError("Theme schema 6 assets must map string keys to string paths.")
        text_assets = payload.get("text_assets")
        if isinstance(text_assets, dict) and any(not isinstance(key, str) or not isinstance(value, str) for key, value in text_assets.items()):
            raise ThemeManifestError("Theme schema 6 text_assets must map string roles to string asset keys.")
        animations = payload.get("animations")
        if isinstance(animations, dict) and any(not isinstance(key, str) or not isinstance(value, dict) for key, value in animations.items()):
            raise ThemeManifestError("Theme schema 6 animations must map string keys to objects.")

    @staticmethod
    def _parse_palette(value: object) -> ThemePaletteDefinition:
        if not isinstance(value, dict):
            raise ThemeAssetError("Theme palette must be an object.")
        unknown = sorted(str(key) for key in value if str(key) not in PALETTE_FIELDS)
        if unknown:
            raise ThemeAssetError(f"Theme palette contains unknown field: {unknown[0]}")
        colors = DEFAULT_THEME_PALETTE.to_dict()
        for key, raw_color in value.items():
            try:
                colors[str(key)] = normalize_hex_color(raw_color, str(key))
            except ValueError as error:
                raise ThemeAssetError(str(error)) from error
        return ThemePaletteDefinition(**colors)

    def _parse_motion(self, value: object) -> ThemeMotionDefinition:
        if not isinstance(value, dict):
            raise ThemeAssetError("Theme motion must be an object.")

        page = self._parse_transition(value.get("page"), ThemeMotionDefinition().page, self.PAGE_TRANSITIONS, "page")
        dialog = self._parse_transition(value.get("dialog"), ThemeMotionDefinition().dialog, self.DIALOG_TRANSITIONS, "dialog")
        launch_control = self._parse_transition(value.get("launch_control"), ThemeMotionDefinition().launch_control, self.LAUNCH_TRANSITIONS, "launch_control")

        raw_button = value.get("button", {})
        if raw_button is None:
            raw_button = {}
        if not isinstance(raw_button, dict):
            raise ThemeAssetError("Theme motion button must be an object.")
        defaults = ThemeMotionDefinition().button
        hover_duration_ms = self._motion_int(raw_button.get("hover_duration_ms", defaults.hover_duration_ms), 0, 2000, "button.hover_duration_ms")
        press_duration_ms = self._motion_int(raw_button.get("press_duration_ms", defaults.press_duration_ms), 0, 2000, "button.press_duration_ms")
        easing = self._motion_easing(raw_button.get("easing", defaults.easing), "button.easing")
        hover_strength = self._motion_float(raw_button.get("hover_strength", defaults.hover_strength), 0.0, 1.0, "button.hover_strength")
        press_strength = self._motion_float(raw_button.get("press_strength", defaults.press_strength), 0.0, 1.0, "button.press_strength")
        if press_strength < hover_strength:
            raise ThemeAssetError("Theme motion button.press_strength must be greater than or equal to hover_strength.")
        button = ButtonMotionDefinition(hover_duration_ms, press_duration_ms, easing, hover_strength, press_strength)

        raw_sidebar = value.get("sidebar", {})
        if raw_sidebar is None:
            raw_sidebar = {}
        if not isinstance(raw_sidebar, dict):
            raise ThemeAssetError("Theme motion sidebar must be an object.")
        sidebar_defaults = ThemeMotionDefinition().sidebar
        sidebar = SidebarMotionDefinition(
            duration_ms=self._motion_int(raw_sidebar.get("duration_ms", sidebar_defaults.duration_ms), 0, 3000, "sidebar.duration_ms"),
            easing=self._motion_easing(raw_sidebar.get("easing", sidebar_defaults.easing), "sidebar.easing"),
            collapsed_width=self._motion_int(raw_sidebar.get("collapsed_width", sidebar_defaults.collapsed_width), 56, 160, "sidebar.collapsed_width"),
        )

        raw_toast = value.get("toast", {})
        if raw_toast is None:
            raw_toast = {}
        if not isinstance(raw_toast, dict):
            raise ThemeAssetError("Theme motion toast must be an object.")
        toast_defaults = ThemeMotionDefinition().toast
        toast_type = str(raw_toast.get("type", toast_defaults.transition_type)).strip().lower()
        if toast_type not in self.TOAST_TRANSITIONS:
            raise ThemeAssetError(f"Theme motion toast.type is invalid: {toast_type!r}")
        toast = ToastMotionDefinition(
            transition_type=toast_type,
            duration_ms=self._motion_int(raw_toast.get("duration_ms", toast_defaults.duration_ms), 0, 3000, "toast.duration_ms"),
            visible_duration_ms=self._motion_int(raw_toast.get("visible_duration_ms", toast_defaults.visible_duration_ms), 500, 30_000, "toast.visible_duration_ms"),
            easing=self._motion_easing(raw_toast.get("easing", toast_defaults.easing), "toast.easing"),
            distance_px=self._motion_int(raw_toast.get("distance_px", toast_defaults.distance_px), 0, 256, "toast.distance_px"),
            max_visible=self._motion_int(raw_toast.get("max_visible", toast_defaults.max_visible), 1, 8, "toast.max_visible"),
        )

        raw_performance = value.get("performance", {})
        if raw_performance is None:
            raw_performance = {}
        if not isinstance(raw_performance, dict):
            raise ThemeAssetError("Theme motion performance must be an object.")
        performance_defaults = ThemeMotionDefinition().performance
        pause_when_hidden = raw_performance.get("pause_when_hidden", performance_defaults.pause_when_hidden)
        if not isinstance(pause_when_hidden, bool):
            raise ThemeAssetError("Theme motion performance.pause_when_hidden must be a boolean.")
        performance = MotionPerformanceDefinition(
            full_fps=self._motion_int(raw_performance.get("full_fps", performance_defaults.full_fps), 15, 120, "performance.full_fps"),
            reduced_fps=self._motion_int(raw_performance.get("reduced_fps", performance_defaults.reduced_fps), 10, 60, "performance.reduced_fps"),
            pause_when_hidden=pause_when_hidden,
        )
        if performance.reduced_fps > performance.full_fps:
            raise ThemeAssetError("Theme motion performance.reduced_fps must not exceed full_fps.")

        return ThemeMotionDefinition(
            page=page,
            dialog=dialog,
            launch_control=launch_control,
            button=button,
            sidebar=sidebar,
            toast=toast,
            performance=performance,
        )

    def _parse_transition(self, value: object, default: MotionTransitionDefinition, allowed_types: frozenset[str], label: str) -> MotionTransitionDefinition:
        if value is None:
            return default
        if not isinstance(value, dict):
            raise ThemeAssetError(f"Theme motion {label} must be an object.")
        transition_type = str(value.get("type", default.transition_type)).strip().lower()
        if transition_type not in allowed_types:
            raise ThemeAssetError(f"Theme motion {label}.type is invalid: {transition_type!r}")
        return MotionTransitionDefinition(
            transition_type=transition_type,
            duration_ms=self._motion_int(value.get("duration_ms", default.duration_ms), 0, 3000, f"{label}.duration_ms"),
            easing=self._motion_easing(value.get("easing", default.easing), f"{label}.easing"),
            distance_px=self._motion_int(value.get("distance_px", default.distance_px), 0, 256, f"{label}.distance_px"),
        )

    def _motion_easing(self, value: object, label: str) -> str:
        easing = str(value).strip().lower()
        if easing not in self.MOTION_EASINGS:
            raise ThemeAssetError(f"Theme motion {label} is invalid: {easing!r}")
        return easing

    @staticmethod
    def _motion_int(value: object, minimum: int, maximum: int, label: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as error:
            raise ThemeAssetError(f"Theme motion {label} must be an integer.") from error
        if not minimum <= parsed <= maximum:
            raise ThemeAssetError(f"Theme motion {label} must be between {minimum} and {maximum}.")
        return parsed

    @staticmethod
    def _motion_float(value: object, minimum: float, maximum: float, label: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as error:
            raise ThemeAssetError(f"Theme motion {label} must be numeric.") from error
        if not minimum <= parsed <= maximum:
            raise ThemeAssetError(f"Theme motion {label} must be between {minimum} and {maximum}.")
        return parsed

    def _parse_animation(self, directory: Path, key: object, value: object) -> ThemeAnimationDefinition:
        normalized_key = str(key).strip().lower()
        if not self.ANIMATION_KEY_PATTERN.fullmatch(normalized_key):
            raise ThemeAssetError(f"Invalid animation key: {key!r}")
        if not isinstance(value, dict):
            raise ThemeAssetError(f"Animation {normalized_key} must be an object.")
        animation_type = str(value.get("type", "spritesheet")).strip().lower()
        if animation_type != "spritesheet":
            raise ThemeAssetError(f"Animation {normalized_key} has unsupported type: {animation_type!r}")

        relative = str(value.get("path") or "").strip()
        candidate = self._safe_png_path(directory, relative)
        try:
            frame_size = value.get("frame_size")
            if not isinstance(frame_size, (list, tuple)) or len(frame_size) != 2:
                raise ValueError
            frame_width = int(frame_size[0])
            frame_height = int(frame_size[1])
            frame_count = int(value.get("frame_count", 0))
            columns = int(value.get("columns", frame_count))
            frame_duration_ms = int(value.get("frame_duration_ms", 100))
        except (TypeError, ValueError) as error:
            raise ThemeAssetError(f"Animation {normalized_key} has invalid frame metadata.") from error

        if frame_width <= 0 or frame_height <= 0 or frame_width > 4096 or frame_height > 4096:
            raise ThemeAssetError(f"Animation {normalized_key} has invalid frame size.")
        if frame_count <= 0 or frame_count > self.MAX_ANIMATION_FRAMES:
            raise ThemeAssetError(f"Animation {normalized_key} frame_count must be between 1 and {self.MAX_ANIMATION_FRAMES}.")
        if columns <= 0 or columns > frame_count:
            raise ThemeAssetError(f"Animation {normalized_key} has invalid columns.")
        if not self.MIN_FRAME_DURATION_MS <= frame_duration_ms <= self.MAX_FRAME_DURATION_MS:
            raise ThemeAssetError(
                f"Animation {normalized_key} frame_duration_ms must be between "
                f"{self.MIN_FRAME_DURATION_MS} and {self.MAX_FRAME_DURATION_MS}."
            )

        render_mode = str(value.get("render_mode", value.get("scale_mode", "tile_x"))).strip().lower()
        if render_mode == "tile":
            render_mode = "tile_x"
        if render_mode not in self.ANIMATION_RENDER_MODES:
            raise ThemeAssetError(f"Animation {normalized_key} has invalid render_mode: {render_mode!r}")
        filtering = str(value.get("filtering", "nearest")).strip().lower()
        if filtering not in self.ANIMATION_FILTERING_MODES:
            raise ThemeAssetError(f"Animation {normalized_key} has invalid filtering: {filtering!r}")

        fallback_asset_value = value.get("fallback_asset", value.get("fallback"))
        fallback_asset = str(fallback_asset_value).strip() if fallback_asset_value is not None else None
        if fallback_asset and fallback_asset not in THEME_ASSET_BY_KEY:
            raise ThemeAssetError(f"Animation {normalized_key} references unknown fallback asset: {fallback_asset}")

        loop_value = value.get("loop", True)
        if not isinstance(loop_value, bool):
            raise ThemeAssetError(f"Animation {normalized_key} loop must be a boolean.")

        return ThemeAnimationDefinition(
            key=normalized_key,
            path=candidate.relative_to(directory.resolve()).as_posix(),
            frame_width=frame_width,
            frame_height=frame_height,
            frame_count=frame_count,
            columns=columns,
            frame_duration_ms=frame_duration_ms,
            loop=loop_value,
            render_mode=render_mode,
            filtering=filtering,
            fallback_asset=fallback_asset,
        )

    def _parse_font(self, directory: Path, value: object) -> ThemeFontDefinition:
        if not isinstance(value, dict):
            raise ThemeAssetError("Theme font must be an object.")

        raw_files = value.get("files")
        if raw_files is None:
            single_path = value.get("path")
            raw_files = [single_path] if single_path is not None else []
        if not isinstance(raw_files, (list, tuple)):
            raise ThemeAssetError("Theme font files must be a list.")
        if not 1 <= len(raw_files) <= self.MAX_FONT_FILES:
            raise ThemeAssetError(f"Theme font must declare between 1 and {self.MAX_FONT_FILES} files.")

        paths: list[str] = []
        for raw_path in raw_files:
            candidate = self._safe_font_path(directory, str(raw_path or ""))
            normalized = candidate.relative_to(directory.resolve()).as_posix()
            if normalized not in paths:
                paths.append(normalized)
        if not paths:
            raise ThemeAssetError("Theme font does not contain a usable font file.")

        raw_family = value.get("family")
        family = str(raw_family).strip() if raw_family is not None else None
        if family == "":
            family = None
        if family is not None and (len(family) > 128 or any(ord(character) < 32 for character in family)):
            raise ThemeAssetError("Theme font family is invalid.")

        try:
            point_size = float(value.get("point_size", 10.5))
            weight = int(value.get("weight", 400))
            letter_spacing = float(value.get("letter_spacing", 0.0))
        except (TypeError, ValueError) as error:
            raise ThemeAssetError("Theme font has invalid numeric metadata.") from error
        if not 6.0 <= point_size <= 72.0:
            raise ThemeAssetError("Theme font point_size must be between 6 and 72.")
        if weight not in self.FONT_WEIGHTS:
            raise ThemeAssetError("Theme font weight must be one of 100, 200, 300, 400, 500, 600, 700, 800, or 900.")
        if not -5.0 <= letter_spacing <= 20.0:
            raise ThemeAssetError("Theme font letter_spacing must be between -5 and 20 pixels.")

        italic = value.get("italic", False)
        if not isinstance(italic, bool):
            raise ThemeAssetError("Theme font italic must be a boolean.")

        raw_fallbacks = value.get("fallback_families", [])
        if not isinstance(raw_fallbacks, (list, tuple)):
            raise ThemeAssetError("Theme font fallback_families must be a list.")
        if len(raw_fallbacks) > 8:
            raise ThemeAssetError("Theme font supports at most 8 fallback families.")
        fallback_families: list[str] = []
        for raw_fallback in raw_fallbacks:
            fallback = str(raw_fallback).strip()
            if not fallback or len(fallback) > 128 or any(ord(character) < 32 for character in fallback):
                raise ThemeAssetError("Theme font contains an invalid fallback family.")
            if fallback not in fallback_families:
                fallback_families.append(fallback)

        return ThemeFontDefinition(
            paths=tuple(paths),
            family=family,
            point_size=point_size,
            weight=weight,
            italic=italic,
            letter_spacing=letter_spacing,
            fallback_families=tuple(fallback_families),
        )

    @staticmethod
    def _parse_capabilities(raw: object, issues: list[str]) -> frozenset[str]:
        if raw is None:
            return frozenset()
        if isinstance(raw, dict):
            return frozenset(str(key).strip() for key, enabled in raw.items() if bool(enabled) and str(key).strip())
        if isinstance(raw, (list, tuple, set)):
            return frozenset(str(value).strip() for value in raw if str(value).strip())
        issues.append("Theme capabilities must be an object or list.")
        return frozenset()

    @classmethod
    def _safe_stylesheet_path(cls, root: Path, relative: str) -> Path:
        value = str(relative).replace("\\", "/").strip()
        if not value or value.startswith("/") or ":" in value.split("/", 1)[0]:
            raise ThemeAssetError(f"Unsafe theme stylesheet path: {relative!r}")
        root_resolved = root.resolve()
        candidate = (root_resolved / value).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ThemeAssetError(f"Theme stylesheet escapes its theme directory: {relative!r}") from error
        if candidate.suffix.lower() != ".qss":
            raise ThemeAssetError(f"Theme stylesheet must be a QSS file: {relative!r}")
        return candidate

    @classmethod
    def _read_stylesheet(cls, path: Path) -> str:
        try:
            size = path.stat().st_size
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ThemeAssetError(f"Unable to read theme stylesheet: {path}") from error
        if size > cls.MAX_STYLESHEET_BYTES:
            raise ThemeAssetError(f"Theme stylesheet exceeds the {cls.MAX_STYLESHEET_BYTES // 1024} KiB limit: {path}")
        lowered = text.casefold()
        if "\x00" in text or "@import" in lowered or "url(" in lowered:
            raise ThemeAssetError("Theme stylesheet may not contain NUL, @import, or url() directives.")
        return text.strip()

    @classmethod
    def _safe_font_path(cls, root: Path, relative: str) -> Path:
        value = str(relative).replace("\\", "/").strip()
        if not value or value.startswith("/") or ":" in value.split("/", 1)[0]:
            raise ThemeAssetError(f"Unsafe theme font path: {relative!r}")
        root_resolved = root.resolve()
        candidate = (root_resolved / value).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ThemeAssetError(f"Theme font escapes its theme directory: {relative!r}") from error
        if candidate.suffix.lower() not in cls.FONT_EXTENSIONS:
            raise ThemeAssetError(f"Theme font must be a TTF or OTF file: {relative!r}")
        return candidate

    @classmethod
    def _validate_font(cls, path: Path) -> int:
        try:
            size = path.stat().st_size
            with path.open("rb") as file:
                signature = file.read(4)
        except OSError as error:
            raise ThemeAssetError(f"Unable to read theme font: {path}") from error
        if size <= 0 or size > cls.MAX_FONT_FILE_BYTES:
            raise ThemeAssetError(
                f"Theme font size must be between 1 byte and {cls.MAX_FONT_FILE_BYTES // (1024 * 1024)} MiB: {path}"
            )
        if signature not in {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"}:
            raise ThemeAssetError(f"Invalid TTF/OTF theme font: {path}")
        return size

    @staticmethod
    def _safe_png_path(root: Path, relative: str) -> Path:
        value = str(relative).replace("\\", "/").strip()
        if not value or value.startswith("/") or ":" in value.split("/", 1)[0]:
            raise ThemeAssetError(f"Unsafe theme asset path: {relative!r}")
        root_resolved = root.resolve()
        candidate = (root_resolved / value).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ThemeAssetError(f"Theme asset escapes its theme directory: {relative!r}") from error
        if candidate.suffix.lower() != ".png":
            raise ThemeAssetError(f"Theme asset must be a PNG: {relative!r}")
        return candidate

    @classmethod
    def _validate_animation_sheet(cls, path: Path, definition: ThemeAnimationDefinition) -> tuple[int, int]:
        width, height = cls._validate_png(path)
        required_rows = definition.rows
        if definition.frame_width * definition.columns > width or definition.frame_height * required_rows > height:
            raise ThemeAssetError(
                f"Animation sprite sheet is too small for {definition.key}: {path} "
                f"({width}x{height}, requires at least "
                f"{definition.frame_width * definition.columns}x{definition.frame_height * required_rows})"
            )
        return width, height

    @staticmethod
    def _validate_png(path: Path) -> tuple[int, int]:
        try:
            with path.open("rb") as file:
                header = file.read(24)
        except OSError as error:
            raise ThemeAssetError(f"Unable to read theme PNG: {path}") from error
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise ThemeAssetError(f"Invalid PNG theme asset: {path}")
        width, height = struct.unpack(">II", header[16:24])
        if width <= 0 or height <= 0 or width > 16384 or height > 16384:
            raise ThemeAssetError(f"Invalid PNG dimensions: {path}")
        return width, height

    @classmethod
    def _fallback_theme(cls) -> ThemeDefinition:
        return ThemeDefinition(theme_id=cls.FALLBACK_THEME_ID, name="Built-in CSS fallback", author="MCW Launcher", root=None, schema_version=THEME_SCHEMA_VERSION, builtin_fallback=True)


theme_manager = ThemeManager()
