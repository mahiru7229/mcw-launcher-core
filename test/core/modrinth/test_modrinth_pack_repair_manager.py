from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import zipfile

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_pack_installer import ModrinthPackInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_pack_repair_manager import ModrinthPackRepairManager
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version
from src.models.modrinth.project import ModrinthProject
from src.models.modrinth.version import ModrinthFile, ModrinthVersion


def test_repair_restores_missing_and_modified_managed_files(monkeypatch, tmp_path: Path) -> None:
    instance_dir = tmp_path / "instances" / "Pack"
    (instance_dir / "config").mkdir(parents=True)
    (instance_dir / "mods").mkdir()
    (instance_dir / "instance.json").write_text('{"id":"id"}', encoding="utf-8")
    (instance_dir / "config" / "pack.cfg").write_bytes(b"USER-BROKEN")
    (instance_dir / "notes.txt").write_text("keep me", encoding="utf-8")
    instance = Instance(instance_id="id", name="Pack", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))

    mod_bytes = b"MOD-FILE"
    override_bytes = b"PACK-CONFIG"
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "v1",
        "name": "Pack",
        "files": [{
            "path": "mods/example.jar",
            "hashes": {"sha1": hashlib.sha1(mod_bytes).hexdigest(), "sha512": hashlib.sha512(mod_bytes).hexdigest()},
            "downloads": ["https://cdn.modrinth.com/data/pack/versions/v1/example.jar"],
            "fileSize": len(mod_bytes),
            "env": {"client": "required", "server": "required"},
        }],
        "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.0"},
    }
    pack_source = tmp_path / "pack.mrpack"
    with zipfile.ZipFile(pack_source, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))
        archive.writestr("overrides/config/pack.cfg", override_bytes)

    ModrinthPackRegistry.save(instance_dir, {
        "projectId": "pack",
        "versionId": "v1",
        "versionNumber": "1.0",
        "minecraftVersion": "1.21.1",
        "loader": "fabric",
        "loaderVersion": "0.16.0",
        "installOptionalFiles": True,
        "managedFiles": [
            {"path": "mods/example.jar", "sha1": hashlib.sha1(mod_bytes).hexdigest(), "sha512": hashlib.sha512(mod_bytes).hexdigest(), "size": len(mod_bytes), "source": "download", "downloads": ["https://cdn.modrinth.com/data/pack/versions/v1/example.jar"]},
            {"path": "config/pack.cfg", "sha1": hashlib.sha1(override_bytes).hexdigest(), "sha512": hashlib.sha512(override_bytes).hexdigest(), "size": len(override_bytes), "source": "overrides"},
        ],
        "preservedFiles": [{"path": "config/pack.cfg", "reason": "modified-by-user"}],
    })

    project = ModrinthProject(project_id="pack", slug="pack", title="Pack", description="", project_type="modpack")
    pack_version = ModrinthVersion(version_id="v1", project_id="pack", name="1.0", version_number="1.0", version_type="release", game_versions=("1.21.1",), loaders=("fabric",), files=(ModrinthFile(url="https://cdn.modrinth.com/pack.mrpack", filename="pack.mrpack", sha1="a", sha512="b", size=1, primary=True),))

    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "BACKUPS_ROOT", tmp_path / "backups")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda _instance: False)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: project)
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: pack_version)
    monkeypatch.setattr(ModrinthDownloader, "download_file", lambda _file, destination, **kwargs: destination.parent.mkdir(parents=True, exist_ok=True) or shutil.copy2(pack_source, destination))

    def fake_download_files(files, staging, reporter=None):
        assert [item["path"] for item in files] == ["mods/example.jar"]
        target = staging / "mods" / "example.jar"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(mod_bytes)

    monkeypatch.setattr(ModrinthPackInstaller, "_download_files", fake_download_files)
    version = Version(id="1.21.1", path=tmp_path / "version.json", libraries=[], downloads={}, asset_index={}, assets="", main_class="", java_version={}, raw_json={}, type="release", arguments={}, minecraft_arguments=None)
    monkeypatch.setattr(VersionManager, "load", lambda _version_id: version)
    monkeypatch.setattr(ModLoaderManager, "resolve", lambda *args, **kwargs: ("fabric", "0.16.0"))
    monkeypatch.setattr(ModLoaderManager, "prepare", lambda *args, **kwargs: version)
    monkeypatch.setattr(InstanceManager, "set_runtime_profile", lambda *_args, **_kwargs: instance)

    result = ModrinthPackRepairManager.repair(instance)

    assert (instance_dir / "mods" / "example.jar").read_bytes() == mod_bytes
    assert (instance_dir / "config" / "pack.cfg").read_bytes() == override_bytes
    assert (instance_dir / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert result.missing_files == 1
    assert result.modified_files == 1
    assert result.repaired_files == 2
    assert result.backup_path is not None and result.backup_path.is_file()
    registry = ModrinthPackRegistry.load_from_dir(instance_dir)
    assert registry["schemaVersion"] == 5
    assert registry["preservedFiles"] == []
    assert len(registry["verificationCache"]) == 2
