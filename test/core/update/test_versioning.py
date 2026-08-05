import pytest

from src.core.update.versioning import LauncherVersion


def test_parse_display_and_tag_versions() -> None:
    assert LauncherVersion.parse("v0.5.0 Beta 2") == LauncherVersion(0, 5, 0, "beta", 2)
    assert LauncherVersion.parse("v0.5.0-beta.3") == LauncherVersion(0, 5, 0, "beta", 3)
    assert LauncherVersion.parse("0.5.0-rc.1") == LauncherVersion(0, 5, 0, "rc", 1)
    assert LauncherVersion.parse("1.0.0") == LauncherVersion(1, 0, 0)
    assert LauncherVersion.parse("v0.7.0.1") == LauncherVersion(0, 7, 0, revision=1)
    assert str(LauncherVersion.parse("0.7.0.1")) == "0.7.0.1"


def test_version_order_handles_prereleases() -> None:
    assert LauncherVersion.parse("0.5.0-alpha.2") < LauncherVersion.parse("0.5.0-beta.1")
    assert LauncherVersion.parse("0.5.0-beta.2") < LauncherVersion.parse("0.5.0-rc.1")
    assert LauncherVersion.parse("0.5.0-rc.1") < LauncherVersion.parse("0.5.0")
    assert LauncherVersion.parse("0.5.0") < LauncherVersion.parse("0.5.1-beta.1")
    assert LauncherVersion.parse("0.7.0") < LauncherVersion.parse("0.7.0.1")
    assert LauncherVersion.parse("0.7.0.1") < LauncherVersion.parse("0.7.1-beta.1")
    assert LauncherVersion.parse("0.7.1-beta.1") < LauncherVersion.parse("0.7.1")
    assert LauncherVersion.parse("0.7.1") < LauncherVersion.parse("0.7.2")


def test_invalid_version_is_rejected() -> None:
    with pytest.raises(ValueError):
        LauncherVersion.parse("Beta 2")
