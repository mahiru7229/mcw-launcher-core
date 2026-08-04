from __future__ import annotations

from dataclasses import dataclass, replace
import re


HEX_COLOR_PATTERN_TEXT = r"^#[0-9A-Fa-f]{6}$"
HEX_COLOR_PATTERN = re.compile(HEX_COLOR_PATTERN_TEXT)


@dataclass(frozen=True)
class ThemePaletteDefinition:
    primary: str = "#63984a"
    primary_hover: str = "#7db45e"
    primary_pressed: str = "#4d7938"
    primary_text: str = "#ffffff"
    focus: str = "#8ed35b"
    selection: str = "#4f6d3c"
    selection_text: str = "#ffffff"
    link: str = "#8ed35b"
    success: str = "#8ed35b"
    warning: str = "#d6a93c"
    error: str = "#c47a7a"
    text_primary: str = "#f4f4f4"
    text_muted: str = "#b8b8b8"
    text_disabled: str = "#777777"
    text_inverse: str = "#111111"

    def to_dict(self) -> dict[str, str]:
        return {
            "primary": self.primary,
            "primary_hover": self.primary_hover,
            "primary_pressed": self.primary_pressed,
            "primary_text": self.primary_text,
            "focus": self.focus,
            "selection": self.selection,
            "selection_text": self.selection_text,
            "link": self.link,
            "success": self.success,
            "warning": self.warning,
            "error": self.error,
            "text_primary": self.text_primary,
            "text_muted": self.text_muted,
            "text_disabled": self.text_disabled,
            "text_inverse": self.text_inverse,
        }


DEFAULT_THEME_PALETTE = ThemePaletteDefinition()
PALETTE_FIELDS = frozenset(DEFAULT_THEME_PALETTE.to_dict())
PRIMARY_PALETTE_FIELDS = frozenset({"primary", "primary_hover", "primary_pressed", "primary_text", "focus", "selection", "selection_text", "link"})
TEXT_PALETTE_FIELDS = frozenset({"text_primary", "text_muted", "text_disabled", "text_inverse"})


def normalize_hex_color(value: object, label: str = "color") -> str:
    text = str(value or "").strip()
    if not HEX_COLOR_PATTERN.fullmatch(text):
        raise ValueError(f"Theme palette {label} must use #RRGGBB format.")
    return text.lower()


def derive_custom_accent(theme_palette: ThemePaletteDefinition, accent: str) -> ThemePaletteDefinition:
    primary = normalize_hex_color(accent, "primary")
    primary_text = _contrast_text(primary)
    return replace(
        theme_palette,
        primary=primary,
        primary_hover=_mix(primary, "#ffffff", 0.18),
        primary_pressed=_mix(primary, "#000000", 0.22),
        primary_text=primary_text,
        focus=_mix(primary, "#ffffff", 0.12),
        selection=_mix(primary, "#000000", 0.34),
        selection_text=_contrast_text(_mix(primary, "#000000", 0.34)),
        link=_mix(primary, "#ffffff", 0.10),
    )




def derive_custom_text(theme_palette: ThemePaletteDefinition, text_color: str) -> ThemePaletteDefinition:
    """Return a palette with a safe custom primary text family.

    Semantic colors are intentionally preserved.  Muted and disabled colors are
    derived from the selected text color so a single launcher override remains
    coherent across labels, controls, and placeholder text.
    """
    primary = normalize_hex_color(text_color, "text_primary")
    muted = _mix(primary, "#777777", 0.34)
    disabled = _mix(primary, "#666666", 0.58)
    return replace(
        theme_palette,
        text_primary=primary,
        text_muted=muted,
        text_disabled=disabled,
        text_inverse=_contrast_text(primary),
    )


def contrast_ratio(foreground: str, background: str) -> float:
    left = _relative_luminance(foreground)
    right = _relative_luminance(background)
    lighter, darker = max(left, right), min(left, right)
    return (lighter + 0.05) / (darker + 0.05)


def is_readable_text(foreground: str, background: str, minimum_ratio: float = 3.0) -> bool:
    return contrast_ratio(foreground, background) >= max(1.0, float(minimum_ratio))

def _mix(left: str, right: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, float(ratio)))
    left_rgb = _rgb(left)
    right_rgb = _rgb(right)
    mixed = tuple(round(a + (b - a) * ratio) for a, b in zip(left_rgb, right_rgb))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _contrast_text(color: str) -> str:
    return "#111111" if _relative_luminance(color) > 0.45 else "#ffffff"


def _relative_luminance(color: str) -> float:
    red, green, blue = (_linear(channel / 255.0) for channel in _rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _rgb(color: str) -> tuple[int, int, int]:
    normalized = normalize_hex_color(color)
    return tuple(int(normalized[index:index + 2], 16) for index in (1, 3, 5))
