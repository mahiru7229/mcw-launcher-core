from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.instance.instance_manager import InstanceManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.forge.forge_change_manager import ForgeChangeManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path, loader: tuple[str, str] = ("forge", "47.3.0")) -> Instance:
    root = tmp_path / "Test"
    root.mkdir(parents=True)
    return Instance(instance_id="instance-id", name="Test", version_id="1.20.1", instance_dir=root, mod_loader=loader)


def patch_change_pipeline(monkeypatch: pytest.MonkeyPatch, instance: Instance) -> None:
    monkeypatch.setattr(VersionManager, "load", lambda version_id: SimpleNamespace(id=version_id))
    monkeypatch.setattr(ModLoaderManager, "prepare", lambda version, loader_name, loader_version, reporter=None: SimpleNamespace(id=f"{loader_name}-{loader_version}"))
    monkeypatch.setattr(ForgeChangeManager, "_verify_prepared", lambda *args, **kwargs: None)

    def set_loader(name: str, loader: tuple[str, str]) -> Instance:
        assert name == instance.name
        instance.mod_loader = tuple(loader)
        return instance

    monkeypatch.setattr(InstanceManager, "set_mod_loader", set_loader)


def test_change_records_previous_loader_only_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    instance = make_instance(tmp_path)
    patch_change_pipeline(monkeypatch, instance)

    result = ForgeChangeManager.change(instance, "forge", "47.4.21")

    assert result.mod_loader == ("forge", "47.4.21")
    snapshot = ForgeChangeManager.load_snapshot(instance)
    assert snapshot is not None
    assert snapshot["previous_loader"] == ["forge", "47.3.0"]
    assert snapshot["target_loader"] == ["forge", "47.4.21"]


def test_failed_change_keeps_current_loader_and_existing_restore_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    instance = make_instance(tmp_path)
    patch_change_pipeline(monkeypatch, instance)
    ForgeChangeManager.change(instance, "forge", "47.4.20")
    original_snapshot = ForgeChangeManager.load_snapshot(instance)

    monkeypatch.setattr(ModLoaderManager, "prepare", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("installer failed")))

    with pytest.raises(RuntimeError, match="installer failed"):
        ForgeChangeManager.change(instance, "forge", "47.4.21")

    assert instance.mod_loader == ("forge", "47.4.20")
    assert ForgeChangeManager.load_snapshot(instance) == original_snapshot


def test_restore_previous_loader_creates_reverse_restore_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    instance = make_instance(tmp_path)
    patch_change_pipeline(monkeypatch, instance)
    ForgeChangeManager.change(instance, "forge", "47.4.21")

    restored = ForgeChangeManager.restore_previous(instance)

    assert restored.mod_loader == ("forge", "47.3.0")
    reverse = ForgeChangeManager.load_snapshot(instance)
    assert reverse is not None
    assert reverse["previous_loader"] == ["forge", "47.4.21"]
    assert reverse["target_loader"] == ["forge", "47.3.0"]


def test_restore_requires_valid_snapshot(tmp_path: Path):
    instance = make_instance(tmp_path)

    with pytest.raises(RuntimeError, match="No previous mod-loader installation"):
        ForgeChangeManager.restore_previous(instance)


def test_change_from_fabric_to_quilt_records_independent_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = make_instance(tmp_path, loader=("fabric", "0.16.10"))
    patch_change_pipeline(monkeypatch, instance)

    result = ForgeChangeManager.change(instance, "quilt", "0.28.0")

    assert result.mod_loader == ("quilt", "0.28.0")
    snapshot = ForgeChangeManager.load_snapshot(instance)
    assert snapshot is not None
    assert snapshot["previous_loader"] == ["fabric", "0.16.10"]
    assert snapshot["target_loader"] == ["quilt", "0.28.0"]

    restored = ForgeChangeManager.restore_previous(instance)
    assert restored.mod_loader == ("fabric", "0.16.10")
