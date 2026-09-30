from src.gui.display_profile import fit_dialog_size, select_display_profile


def test_full_hd_screen_uses_1600_by_900_profile() -> None:
    profile = select_display_profile(1920, 1080)

    assert profile.name == "full-hd"
    assert (profile.window_width, profile.window_height) == (1600, 900)
    assert (profile.sidebar_width, profile.right_panel_width) == (220, 400)
    assert profile.compact is False


def test_1366_by_768_screen_uses_1280_by_720_compact_profile() -> None:
    profile = select_display_profile(1366, 768)

    assert profile.name == "hd"
    assert (profile.window_width, profile.window_height) == (1280, 720)
    assert (profile.sidebar_width, profile.right_panel_width) == (188, 330)
    assert profile.compact is True


def test_smaller_screen_uses_safe_dimensions_inside_screen() -> None:
    profile = select_display_profile(1280, 720)

    assert profile.compact is True
    assert profile.window_width <= 1280
    assert profile.window_height <= 720


def test_large_dialog_is_reduced_to_available_1366_screen_height() -> None:
    size = fit_dialog_size(1366, 728, 1260, 760, 900, 560)

    assert size == (1260, 680)


def test_dialog_keeps_preferred_size_when_screen_has_room() -> None:
    size = fit_dialog_size(1920, 1040, 1260, 760, 900, 560)

    assert size == (1260, 760)
