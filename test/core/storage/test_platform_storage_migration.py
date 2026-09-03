from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.fs.paths import Paths
from src.core.storage.platform_storage_migration import PlatformStorageMigration


@pytest.fixture(autouse=True)
def restore_paths():
    snapshot = Paths.snapshot()
    try:
        yield
    finally:
        Paths.restore(snapshot)


def _configure_xdg(project: Path, xdg: Path) -> None:
    Paths.configure(project, initialize=False)
    Paths.configure_application_defaults(
        platform_name="linux",
        environ={
            "XDG_CONFIG_HOME": str(xdg / "config"),
            "XDG_DATA_HOME": str(xdg / "data"),
            "XDG_CACHE_HOME": str(xdg / "cache"),
            "XDG_STATE_HOME": str(xdg / "state"),
        },
        home=xdg / "home",
    )


def test_migration_copies_legacy_data_and_preserves_source(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config" / "launcher_settings.json").write_text('{"language":"vi-VN"}', encoding="utf-8")
    (project / "instances" / "Vanilla" / "saves").mkdir(parents=True)
    (project / "instances" / "Vanilla" / "saves" / "level.dat").write_bytes(b"world")
    (project / "themes" / "mcw-default").mkdir(parents=True)
    (project / "themes" / "mcw-default" / "theme.json").write_text("{}", encoding="utf-8")
    _configure_xdg(project, tmp_path / "xdg")

    report = PlatformStorageMigration.migrate(project)

    assert report.completed is True
    assert report.copied_files == 3
    assert (Paths.CONFIG_ROOT / "launcher_settings.json").is_file()
    assert (Paths.INSTANCES_ROOT / "Vanilla" / "saves" / "level.dat").read_bytes() == b"world"
    assert (Paths.THEME_ROOT / "mcw-default" / "theme.json").is_file()
    assert (project / "instances" / "Vanilla" / "saves" / "level.dat").is_file()
    marker = json.loads((Paths.CONFIG_ROOT / PlatformStorageMigration.MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["complete"] is True
    assert marker["legacyDataPreserved"] is True

    repeated = PlatformStorageMigration.migrate(project)
    assert repeated.already_completed is True
    assert repeated.copied_files == 0


def test_migration_never_overwrites_a_conflicting_destination(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config" / "launcher_settings.json").write_text("legacy", encoding="utf-8")
    _configure_xdg(project, tmp_path / "xdg")
    Paths.CONFIG_ROOT.mkdir(parents=True)
    target = Paths.CONFIG_ROOT / "launcher_settings.json"
    target.write_text("current", encoding="utf-8")

    report = PlatformStorageMigration.migrate(project)

    assert target.read_text(encoding="utf-8") == "current"
    assert target.as_posix() in report.conflicts
    assert report.errors == ()
