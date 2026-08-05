from __future__ import annotations

import pytest

from src.core.theme.theme_palette import DEFAULT_THEME_PALETTE, contrast_ratio, derive_custom_accent, derive_custom_text, is_readable_text, normalize_hex_color


def test_custom_accent_changes_primary_roles_but_preserves_semantic_colors() -> None:
    palette = derive_custom_accent(DEFAULT_THEME_PALETTE, "#B26CFF")

    assert palette.primary == "#b26cff"
    assert palette.primary_hover != palette.primary
    assert palette.primary_pressed != palette.primary
    assert palette.focus != DEFAULT_THEME_PALETTE.focus
    assert palette.success == DEFAULT_THEME_PALETTE.success
    assert palette.warning == DEFAULT_THEME_PALETTE.warning
    assert palette.error == DEFAULT_THEME_PALETTE.error


def test_hex_colors_are_normalized_and_invalid_values_are_rejected() -> None:
    assert normalize_hex_color("#12ABef") == "#12abef"
    with pytest.raises(ValueError):
        normalize_hex_color("blue")


def test_custom_text_changes_text_family_but_preserves_semantic_colors() -> None:
    palette = derive_custom_text(DEFAULT_THEME_PALETTE, "#D6E8FF")

    assert palette.text_primary == "#d6e8ff"
    assert palette.text_muted != palette.text_primary
    assert palette.text_disabled != palette.text_primary
    assert palette.success == DEFAULT_THEME_PALETTE.success
    assert palette.warning == DEFAULT_THEME_PALETTE.warning
    assert palette.error == DEFAULT_THEME_PALETTE.error
    assert palette.link == DEFAULT_THEME_PALETTE.link


def test_text_contrast_helpers_detect_readable_and_unreadable_pairs() -> None:
    assert contrast_ratio("#ffffff", "#000000") > 20
    assert is_readable_text("#ffffff", "#111111") is True
    assert is_readable_text("#303030", "#313131") is False
