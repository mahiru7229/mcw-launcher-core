from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mcw_core.models import InstanceRuntimeProfile
from mcw_core.services import InstanceService
from src.models.instance.settings import InstanceSettings


def _instance(tmp_path: Path, loader=("forge", "47.2.0")) -> SimpleNamespace:
    return SimpleNamespace(name="Test", version_id="1.20.1", instance_dir=tmp_path, mod_loader=loader)


def test_runtime_profile_reports_components_and_java_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    monkeypatch.setattr(InstanceService, "load", staticmethod(lambda _name: instance))
    monkeypatch.setattr("mcw_core.services.VersionManager.load", lambda _version: SimpleNamespace(java_version={"majorVersion": 17}))
    monkeypatch.setattr("mcw_core.services.SettingsManager.load", lambda _instance: InstanceSettings(java_path=""))

    profile = InstanceService.runtime_profile("Test")

    assert isinstance(profile, InstanceRuntimeProfile)
    assert profile.minecraft_version == "1.20.1"
    assert profile.loader_name == "forge"
    assert profile.loader_version == "47.2.0"
    assert profile.required_java_major == 17
    assert profile.managed_java_major == 17
    assert profile.java_automatic is True
    assert profile.configured_java_path == ""


def test_set_java_runtime_accepts_automatic_without_touching_java_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    updated: list[str] = []
    monkeypatch.setattr(InstanceService, "load", staticmethod(lambda _name: instance))
    monkeypatch.setattr(InstanceService, "is_running", staticmethod(lambda _instance: False))
    monkeypatch.setattr("mcw_core.services.SettingsManager.update_java_path", lambda _instance, path: updated.append(path))
    monkeypatch.setattr("mcw_core.services.VersionManager.load", lambda _version: SimpleNamespace(java_version={"majorVersion": 17}))
    monkeypatch.setattr("mcw_core.services.SettingsManager.load", lambda _instance: InstanceSettings(java_path=""))

    result = InstanceService.set_java_runtime("Test", "")

    assert result.java_automatic is True
    assert updated == [""]


def test_set_java_runtime_rejects_incompatible_custom_java(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    java = tmp_path / "javaw.exe"
    java.write_bytes(b"")
    monkeypatch.setattr(InstanceService, "load", staticmethod(lambda _name: instance))
    monkeypatch.setattr(InstanceService, "is_running", staticmethod(lambda _instance: False))
    monkeypatch.setattr("mcw_core.services.VersionManager.load", lambda _version: SimpleNamespace(java_version={"majorVersion": 17}))
    monkeypatch.setattr("mcw_core.services.JavaManager.normalize_executable", lambda path: Path(path))
    monkeypatch.setattr("mcw_core.services.JavaManager.get_major_version", lambda _path: 8)

    with pytest.raises(RuntimeError, match="incompatible"):
        InstanceService.set_java_runtime("Test", str(java))


def test_set_java_runtime_blocks_running_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    instance = _instance(tmp_path)
    monkeypatch.setattr(InstanceService, "load", staticmethod(lambda _name: instance))
    monkeypatch.setattr(InstanceService, "is_running", staticmethod(lambda _instance: True))

    with pytest.raises(RuntimeError, match="Close Minecraft"):
        InstanceService.set_java_runtime("Test", "")
