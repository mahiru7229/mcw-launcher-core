from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.system.memory import SystemMemory


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 16_384))
    return tmp_path


def _defaults(max_memory: int, java_path: str = "") -> dict:
    data = SettingsManager.default_dict()
    data["java"]["path"] = java_path
    data["java"]["min_memory"] = 1536
    data["java"]["max_memory"] = max_memory
    data["java"]["arguments"] = ["-XX:+UseG1GC"]
    data["window"]["width"] = 1600
    data["window"]["height"] = 900
    data["launch"]["game_arguments"] = ["--demo"]
    data["launch"]["lan_connection_provider"] = "e4mc"
    data["launch"]["curseforge_failure_policy"] = "allow"
    return data


def _write_package(path: Path, name: str, settings: dict | None) -> Path:
    package_metadata = {
        "format": "mcwpack",
        "format_version": 1,
        "package_type": "instance",
        "launcher_name": "mcw-launcher",
        "launcher_version": "v0.10.0-beta.1",
        "created_at": "2026-07-28T00:00:00+00:00",
        "include_saves": False,
    }
    instance_metadata = {
        "id": f"{name}-id",
        "name": name,
        "version_id": "1.20.4",
        "mod_loader": ["fabric", "0.16.14"],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("package.json", json.dumps(package_metadata))
        archive.writestr("instance/instance.json", json.dumps(instance_metadata))
        if settings is not None:
            archive.writestr("instance/settings.json", json.dumps(settings))
    return path


def test_new_instance_copies_launcher_defaults(isolated_paths: Path) -> None:
    expected = _defaults(6144)
    LauncherSettingsManager().save({"instance_defaults": expected})

    instance = InstanceManager.create("Global Defaults", SimpleNamespace(id="1.20.4"))

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved == SettingsManager.normalize_dict(expected)


def test_explicit_creation_settings_override_launcher_defaults(isolated_paths: Path) -> None:
    LauncherSettingsManager().save({"instance_defaults": _defaults(6144)})
    explicit = _defaults(4096, "C:/Java/bin/javaw.exe")

    instance = InstanceManager.create(
        "Explicit Defaults",
        SimpleNamespace(id="1.20.4"),
        settings=explicit,
    )

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved == SettingsManager.normalize_dict(explicit)


def test_import_preview_reads_package_settings_without_extracting(isolated_paths: Path) -> None:
    package_settings = _defaults(4096)
    package = _write_package(isolated_paths / "preview.mcwpack", "Preview Pack", package_settings)

    preview = InstanceManager.inspect_import(package)

    assert preview.name == "Preview Pack"
    assert preview.version_id == "1.20.4"
    assert preview.mod_loader == ("fabric", "0.16.14")
    assert preview.has_package_settings is True
    assert preview.settings == SettingsManager.normalize_dict(package_settings)
    assert not (package.parent / ".mcwpack-inspection").exists()


def test_import_can_keep_package_settings(isolated_paths: Path) -> None:
    package_settings = _defaults(4096)
    package = _write_package(isolated_paths / "keep.mcwpack", "Keep Settings", package_settings)

    instance = InstanceManager.import_instance(package)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved == SettingsManager.normalize_dict(package_settings)


def test_import_can_overwrite_package_settings(isolated_paths: Path) -> None:
    package = _write_package(isolated_paths / "overwrite.mcwpack", "Overwrite Settings", _defaults(4096))
    override = _defaults(7168, "D:/Java/bin/javaw.exe")

    instance = InstanceManager.import_instance(package, settings_override=override)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved == SettingsManager.normalize_dict(override)


def test_import_without_settings_uses_launcher_defaults(isolated_paths: Path) -> None:
    expected = _defaults(5120)
    LauncherSettingsManager().save({"instance_defaults": expected})
    package = _write_package(isolated_paths / "missing.mcwpack", "Missing Settings", None)

    preview = InstanceManager.inspect_import(package)
    instance = InstanceManager.import_instance(package)

    assert preview.has_package_settings is False
    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved == SettingsManager.normalize_dict(expected)
