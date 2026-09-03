from __future__ import annotations

from pathlib import Path

import pytest

from src.core.fs.paths import Paths


@pytest.fixture(autouse=True)
def restore_paths():
    snapshot = Paths.snapshot()
    try:
        yield
    finally:
        Paths.restore(snapshot)


def test_linux_application_defaults_follow_xdg_roots(tmp_path: Path) -> None:
    project = tmp_path / "project"
    Paths.configure(project, initialize=False)
    environment = {
        "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
        "XDG_DATA_HOME": str(tmp_path / "xdg-data"),
        "XDG_CACHE_HOME": str(tmp_path / "xdg-cache"),
        "XDG_STATE_HOME": str(tmp_path / "xdg-state"),
    }

    changed = Paths.configure_application_defaults(
        platform_name="linux",
        environ=environment,
        home=tmp_path / "home",
    )

    assert changed is True
    assert Paths.PROJECT_ROOT == project.resolve()
    assert Paths.CONFIG_ROOT == tmp_path / "xdg-config" / "mcw-launcher"
    assert Paths.INSTANCES_ROOT == tmp_path / "xdg-data" / "mcw-launcher" / "instances"
    assert Paths.ACCOUNTS_ROOT == tmp_path / "xdg-data" / "mcw-launcher" / "accounts"
    assert Paths.RUNTIMES_ROOT == tmp_path / "xdg-data" / "mcw-launcher" / "runtimes"
    assert Paths.CACHE_ROOT == tmp_path / "xdg-cache" / "mcw-launcher"
    assert Paths.LOGS_ROOT == tmp_path / "xdg-state" / "mcw-launcher" / "logs"
    assert Paths.uses_platform_storage() is True


def test_relative_xdg_value_falls_back_to_home(tmp_path: Path) -> None:
    Paths.configure(tmp_path / "project", initialize=False)

    Paths.configure_application_defaults(
        platform_name="linux",
        environ={"XDG_CONFIG_HOME": "relative/config"},
        home=tmp_path / "home",
    )

    assert Paths.CONFIG_ROOT == tmp_path / "home" / ".config" / "mcw-launcher"


@pytest.mark.parametrize("portable", ["1", "true", "YES", "on"])
def test_portable_mode_keeps_project_layout(tmp_path: Path, portable: str) -> None:
    project = tmp_path / "portable"
    Paths.configure(project, initialize=False)

    changed = Paths.configure_application_defaults(
        platform_name="linux",
        environ={"MCW_PORTABLE": portable},
        home=tmp_path / "home",
    )

    assert changed is False
    assert Paths.CACHE_ROOT == project / "cache"
    assert Paths.CONFIG_ROOT == project / "config"
    assert Paths.uses_platform_storage() is False


def test_windows_keeps_existing_layout(tmp_path: Path) -> None:
    project = tmp_path / "windows"
    Paths.configure(project, initialize=False)

    assert Paths.configure_application_defaults(platform_name="windows", environ={}, home=tmp_path) is False
    assert Paths.INSTANCES_ROOT == project / "instances"
