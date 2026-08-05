import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.java.java_resolver import JavaResolver
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.version_manager import VersionManager
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.runtime.instance_repair_manager import InstanceRepairManager
from src.models.progress.progress_stage import ProgressStage


@pytest.fixture
def instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance_dir = tmp_path / "instances" / "Repair Test"
    instance_dir.mkdir(parents=True)
    monkeypatch.setattr(Paths, "load_instance_dir", lambda name: instance_dir)
    return SimpleNamespace(name="Repair Test", version_id="1.21.1", mod_loader=("fabric", "0.16.9"), instance_dir=instance_dir)


def test_repair_verifies_pipeline_and_preserves_user_data(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    version = SimpleNamespace(id="fabric-loader-0.16.9-1.21.1", java_version={"majorVersion": 21})
    client_path = Path(instance.instance_dir) / "cache-client.jar"
    assets_root = Path(instance.instance_dir) / "assets"
    natives_dir = Path(instance.instance_dir) / "natives"
    natives_dir.mkdir()
    (natives_dir / "old.dll").write_bytes(b"old")
    marker_dir = natives_dir / ".extracted"
    marker_dir.mkdir()
    (marker_dir / "native-sha1").touch()
    mods_file = Path(instance.instance_dir) / "mods" / "keep.jar"
    save_file = Path(instance.instance_dir) / "saves" / "World" / "level.dat"
    mods_file.parent.mkdir(parents=True)
    save_file.parent.mkdir(parents=True)
    mods_file.write_bytes(b"mod")
    save_file.write_bytes(b"world")
    events = []

    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, received: False))
    monkeypatch.setattr(VersionManifestManager, "get", staticmethod(lambda: []))
    monkeypatch.setattr(ModLoaderManager, "repair", staticmethod(lambda received, reporter=None: version))
    monkeypatch.setattr(DownloadClientManager, "load", staticmethod(lambda **kwargs: client_path))
    monkeypatch.setattr(DownloadLibraryManager, "load", staticmethod(lambda **kwargs: [Path("a.jar"), Path("b.jar")]))
    monkeypatch.setattr(AssetManager, "load", staticmethod(lambda **kwargs: assets_root))
    monkeypatch.setattr(JavaResolver, "resolve", staticmethod(lambda major, reporter=None: Path("C:/Java21/javaw.exe")))
    monkeypatch.setattr(Paths, "natives", staticmethod(lambda received: natives_dir))

    result = InstanceRepairManager.repair(instance, on_progress=events.append)

    assert result.instance_name == "Repair Test"
    assert result.libraries_checked == 2
    assert result.java_path == Path("C:/Java21/javaw.exe")
    assert (natives_dir / "old.dll").exists()
    assert not marker_dir.exists()
    assert mods_file.read_bytes() == b"mod"
    assert save_file.read_bytes() == b"world"
    assert events[0].stage is ProgressStage.REPAIRING_INSTANCE
    assert events[-1].stage is ProgressStage.FINISHED

    report = json.loads(Paths.instance_repair_report(instance).read_text(encoding="utf-8"))
    assert report["instance_name"] == "Repair Test"
    assert report["libraries_checked"] == 2


def test_repair_vanilla_uses_version_manager(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    instance.mod_loader = ("vanilla", "-1")
    version = SimpleNamespace(id="1.21.1", java_version={"majorVersion": 21})
    called = []

    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, received: False))
    monkeypatch.setattr(VersionManifestManager, "get", staticmethod(lambda: []))
    monkeypatch.setattr(VersionManager, "load", staticmethod(lambda version_id: called.append(version_id) or version))
    monkeypatch.setattr(DownloadClientManager, "load", staticmethod(lambda **kwargs: Path("client.jar")))
    monkeypatch.setattr(DownloadLibraryManager, "load", staticmethod(lambda **kwargs: []))
    monkeypatch.setattr(AssetManager, "load", staticmethod(lambda **kwargs: Path("assets")))
    monkeypatch.setattr(JavaResolver, "resolve", staticmethod(lambda major, reporter=None: Path("javaw.exe")))
    monkeypatch.setattr(Paths, "natives", staticmethod(lambda received: Path(instance.instance_dir) / "missing-natives"))

    result = InstanceRepairManager.repair(instance)

    assert called == ["1.21.1"]
    assert result.mod_loader == "vanilla"


def test_repair_is_blocked_while_instance_runs(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, received: True))

    with pytest.raises(RuntimeError, match="Close Minecraft"):
        InstanceRepairManager.repair(instance)


def test_repair_forge_uses_mod_loader_repair(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    instance.mod_loader = ("forge", "47.4.21")
    version = SimpleNamespace(id="forge-1.20.1-47.4.21", java_version={"majorVersion": 17})
    repaired = []

    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, received: False))
    monkeypatch.setattr(VersionManifestManager, "get", staticmethod(lambda: []))
    monkeypatch.setattr(ModLoaderManager, "repair", staticmethod(lambda received, reporter=None: repaired.append(received) or version))
    monkeypatch.setattr(DownloadClientManager, "load", staticmethod(lambda **kwargs: Path("client.jar")))
    monkeypatch.setattr(DownloadLibraryManager, "load", staticmethod(lambda **kwargs: []))
    monkeypatch.setattr(AssetManager, "load", staticmethod(lambda **kwargs: Path("assets")))
    monkeypatch.setattr(JavaResolver, "resolve", staticmethod(lambda major, reporter=None: Path("javaw.exe")))
    monkeypatch.setattr(Paths, "natives", staticmethod(lambda received: Path(instance.instance_dir) / "missing-natives"))

    result = InstanceRepairManager.repair(instance)

    assert repaired == [instance]
    assert result.mod_loader == "forge 47.4.21"
