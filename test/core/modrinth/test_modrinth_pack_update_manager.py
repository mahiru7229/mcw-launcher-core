from __future__ import annotations

from pathlib import Path

from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_pack_update_manager import ModrinthPackUpdateManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.project import ModrinthProject
from src.models.modrinth.version import ModrinthVersion


def make_version(version_id: str, number: str, published: str) -> ModrinthVersion:
    return ModrinthVersion(version_id=version_id, project_id="pack", name=number, version_number=number, version_type="release", game_versions=("1.21.1",), loaders=("fabric",), files=(), date_published=published)


def test_check_returns_only_newer_pack_version(monkeypatch, tmp_path: Path) -> None:
    instance = Instance(instance_id="id", name="Pack", version_id="1.21.1", instance_dir=tmp_path, mod_loader=("fabric", "0.16"))
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {"projectId": "pack", "versionId": "v1", "versionNumber": "1.0"})
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: ModrinthProject(project_id="pack", slug="pack", title="Pack", description="", project_type="modpack"))
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: make_version("v1", "1.0", "2026-01-01T00:00:00Z"))
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda *args, **kwargs: [make_version("v2", "2.0", "2026-02-01T00:00:00Z"), make_version("v1", "1.0", "2026-01-01T00:00:00Z")])

    info = ModrinthPackUpdateManager.check(instance, ("release",))

    assert info is not None
    assert info.available
    assert info.target_version_id == "v2"
    assert info.target_version_number == "2.0"


def test_pack_registry_schema_four_preserves_conflict_metadata(tmp_path: Path) -> None:
    ModrinthPackRegistry.save(tmp_path, {"projectId": "pack", "managedFiles": [], "preservedFiles": [{"path": "config/demo.json", "reason": "modified-by-user", "previousSha1": "AA", "targetSha1": "BB"}]})
    data = ModrinthPackRegistry.load_from_dir(tmp_path)
    assert data["schemaVersion"] == 5
    assert data["preservedFiles"] == [{"path": "config/demo.json", "reason": "modified-by-user", "previousSha1": "aa", "targetSha1": "bb"}]


def test_update_preserves_modified_files_and_replaces_managed_pack_files(monkeypatch, tmp_path: Path) -> None:
    import hashlib
    import json
    import zipfile
    from types import SimpleNamespace

    from src.core.backup.instance_backup_manager import InstanceBackupManager
    from src.core.fs.paths import Paths
    from src.core.instance.instance_manager import InstanceManager
    from src.core.instance.instance_run_lock import InstanceRunLock
    from src.core.minecraft.version_manager import VersionManager
    from src.core.modloader.mod_loader_manager import ModLoaderManager
    from src.core.modrinth.modrinth_downloader import ModrinthDownloader
    from src.core.modrinth.modrinth_pack_installer import ModrinthPackInstaller
    from src.models.minecraft.version import Version
    from src.models.modrinth.version import ModrinthFile

    instance_dir = tmp_path / "instances" / "Pack"
    (instance_dir / "config").mkdir(parents=True)
    (instance_dir / "mods").mkdir()
    (instance_dir / "instance.json").write_text('{"id":"id"}', encoding="utf-8")
    (instance_dir / "config" / "user.cfg").write_bytes(b"USER-MODIFIED")
    (instance_dir / "mods" / "remove.jar").write_bytes(b"REMOVE")
    (instance_dir / "mods" / "unchanged.jar").write_bytes(b"UNCHANGED")
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.15"))

    old_config_hash = hashlib.sha1(b"OLD-CONFIG").hexdigest()
    remove_hash = hashlib.sha1(b"REMOVE").hexdigest()
    unchanged_sha1 = hashlib.sha1(b"UNCHANGED").hexdigest()
    unchanged_sha512 = hashlib.sha512(b"UNCHANGED").hexdigest()
    ModrinthPackRegistry.save(instance_dir, {
        "projectId": "pack",
        "versionId": "v1",
        "versionNumber": "1.0",
        "installOptionalFiles": True,
        "managedFiles": [
            {"path": "config/user.cfg", "sha1": old_config_hash, "sha512": "", "size": 10, "source": "overrides"},
            {"path": "mods/remove.jar", "sha1": remove_hash, "sha512": "", "size": 6, "source": "download"},
            {"path": "mods/unchanged.jar", "sha1": unchanged_sha1, "sha512": unchanged_sha512, "size": 9, "source": "download", "downloads": ["https://cdn.modrinth.com/data/pack/versions/v2/unchanged.jar"]},
        ],
    })

    new_bytes = b"NEW-JAR"
    new_sha1 = hashlib.sha1(new_bytes).hexdigest()
    new_sha512 = hashlib.sha512(new_bytes).hexdigest()
    pack_source = tmp_path / "target.mrpack"
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "v2",
        "name": "Pack",
        "files": [
            {
                "path": "mods/new.jar",
                "hashes": {"sha1": new_sha1, "sha512": new_sha512},
                "downloads": ["https://cdn.modrinth.com/data/pack/versions/v2/new.jar"],
                "fileSize": len(new_bytes),
                "env": {"client": "required", "server": "required"},
            },
            {
                "path": "mods/unchanged.jar",
                "hashes": {"sha1": unchanged_sha1, "sha512": unchanged_sha512},
                "downloads": ["https://cdn.modrinth.com/data/pack/versions/v2/unchanged.jar"],
                "fileSize": 9,
                "env": {"client": "required", "server": "required"},
            },
        ],
        "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.0"},
    }
    with zipfile.ZipFile(pack_source, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))
        archive.writestr("overrides/config/user.cfg", b"PACK-NEW-CONFIG")

    target = ModrinthVersion(version_id="v2", project_id="pack", name="2.0", version_number="2.0", version_type="release", game_versions=("1.21.1",), loaders=("fabric",), files=(ModrinthFile(url="https://cdn.modrinth.com/target.mrpack", filename="target.mrpack", sha1="a", sha512="b", size=1, primary=True),), date_published="2026-02-01T00:00:00Z")
    project = ModrinthProject(project_id="pack", slug="pack", title="Pack", description="", project_type="modpack")

    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "BACKUPS_ROOT", tmp_path / "backups")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda _instance: False)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: project)
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: target)
    monkeypatch.setattr(ModrinthDownloader, "download_file", lambda _file, destination, force=False: destination.parent.mkdir(parents=True, exist_ok=True) or shutil.copy2(pack_source, destination))

    def fake_download_files(files, staging):
        assert [item["path"] for item in files] == ["mods/new.jar"]
        path = staging / "mods" / "new.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_bytes)

    import shutil
    monkeypatch.setattr(ModrinthPackInstaller, "_download_files", fake_download_files)
    version = Version(id="1.21.1", path=tmp_path / "version.json", libraries=[], downloads={}, asset_index={}, assets="", main_class="", java_version={}, raw_json={}, type="release", arguments={}, minecraft_arguments=None)
    monkeypatch.setattr(VersionManager, "load", lambda _version_id: version)
    monkeypatch.setattr(ModLoaderManager, "resolve", lambda *args, **kwargs: ("fabric", "0.16.0"))
    monkeypatch.setattr(ModLoaderManager, "prepare", lambda *args, **kwargs: version)

    def set_profile(_name, new_version, loader):
        instance.version_id = new_version.id
        instance.mod_loader = loader
        return instance

    monkeypatch.setattr(InstanceManager, "set_runtime_profile", set_profile)

    result = ModrinthPackUpdateManager.update(instance, target_version_id="v2", allowed_version_types=("release",))

    assert (instance_dir / "config" / "user.cfg").read_bytes() == b"USER-MODIFIED"
    assert not (instance_dir / "mods" / "remove.jar").exists()
    assert (instance_dir / "mods" / "new.jar").read_bytes() == new_bytes
    assert (instance_dir / "mods" / "unchanged.jar").read_bytes() == b"UNCHANGED"
    assert result.target_version == "2.0"
    assert result.preserved_files == ("config/user.cfg",)
    assert result.backup_path.is_file()
    assert result.unchanged_files == 1
    updated_registry = ModrinthPackRegistry.load_from_dir(instance_dir)
    assert updated_registry["versionId"] == "v2"
    assert updated_registry["preservedFiles"][0]["path"] == "config/user.cfg"


def test_check_uses_loader_saved_by_forge_modpack(monkeypatch, tmp_path: Path) -> None:
    instance = Instance(instance_id="id", name="Forge Pack", version_id="1.20.1", instance_dir=tmp_path, mod_loader=("forge", "47.4.21"))
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {"projectId": "pack", "versionId": "v1", "versionNumber": "1.0", "minecraftVersion": "1.20.1", "loader": "forge"})
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: ModrinthProject(project_id="pack", slug="pack", title="Forge Pack", description="", project_type="modpack"))
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: make_version("v1", "1.0", "2026-01-01T00:00:00Z"))
    seen = []
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda project_id, loader, **kwargs: seen.append((loader, kwargs.get("game_version"))) or [])

    info = ModrinthPackUpdateManager.check(instance, ("release",))

    assert info is not None
    assert seen == [("forge", "1.20.1")]


def test_check_reports_each_metadata_stage(monkeypatch, tmp_path: Path) -> None:
    instance = Instance(instance_id="id", name="Pack", version_id="1.21.1", instance_dir=tmp_path, mod_loader=("fabric", "0.16"))
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {"projectId": "pack", "versionId": "v1", "versionNumber": "1.0"})
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: ModrinthProject(project_id="pack", slug="pack", title="Pack", description="", project_type="modpack"))
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: make_version("v1", "1.0", "2026-01-01T00:00:00Z"))
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda *args, **kwargs: [])
    events = []

    ModrinthPackUpdateManager.check(instance, ("release",), reporter=ProgressReporter(events.append))

    assert [event.current for event in events] == [0, 1, 2, 3, 4, 5]
    assert all(event.total == 5 for event in events)
    assert events[-1].message == "modpack.update_check.checked"


def test_preview_reports_exact_changes_without_mutating_instance(monkeypatch, tmp_path: Path) -> None:
    import hashlib
    import json
    import shutil
    import zipfile

    from src.core.fs.paths import Paths
    from src.core.instance.instance_run_lock import InstanceRunLock
    from src.core.modrinth.modrinth_downloader import ModrinthDownloader
    from src.models.modrinth.version import ModrinthFile

    instance_dir = tmp_path / "instances" / "Preview Pack"
    (instance_dir / "config").mkdir(parents=True)
    (instance_dir / "mods").mkdir()
    (instance_dir / "config" / "user.cfg").write_bytes(b"USER")
    (instance_dir / "mods" / "remove.jar").write_bytes(b"REMOVE")
    (instance_dir / "mods" / "same.jar").write_bytes(b"SAME")
    instance = Instance(
        instance_id="preview-id",
        name="Preview Pack",
        version_id="1.20.1",
        instance_dir=instance_dir,
        mod_loader=("fabric", "0.15"),
    )

    def sha1(data: bytes) -> str:
        return hashlib.sha1(data, usedforsecurity=False).hexdigest()

    ModrinthPackRegistry.save(
        instance_dir,
        {
            "projectId": "pack",
            "versionId": "v1",
            "versionNumber": "1.0",
            "minecraftVersion": "1.20.1",
            "loader": "fabric",
            "loaderVersion": "0.15",
            "installOptionalFiles": True,
            "managedFiles": [
                {"path": "config/user.cfg", "sha1": sha1(b"OLD"), "size": 3, "source": "overrides"},
                {"path": "mods/remove.jar", "sha1": sha1(b"REMOVE"), "size": 6, "source": "download"},
                {"path": "mods/same.jar", "sha1": sha1(b"SAME"), "size": 4, "source": "download"},
            ],
        },
    )

    new_bytes = b"NEW"
    pack_source = tmp_path / "preview.mrpack"
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "versionId": "v2",
        "name": "Preview Pack",
        "files": [
            {
                "path": "mods/new.jar",
                "hashes": {"sha1": sha1(new_bytes), "sha512": hashlib.sha512(new_bytes).hexdigest()},
                "downloads": ["https://cdn.modrinth.com/new.jar"],
                "fileSize": len(new_bytes),
                "env": {"client": "required", "server": "required"},
            },
            {
                "path": "mods/same.jar",
                "hashes": {"sha1": sha1(b"SAME"), "sha512": hashlib.sha512(b"SAME").hexdigest()},
                "downloads": ["https://cdn.modrinth.com/same.jar"],
                "fileSize": 4,
                "env": {"client": "required", "server": "required"},
            },
        ],
        "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.0"},
    }
    with zipfile.ZipFile(pack_source, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))
        archive.writestr("overrides/config/user.cfg", b"PACK")

    target = ModrinthVersion(
        version_id="v2",
        project_id="pack",
        name="2.0",
        version_number="2.0",
        version_type="release",
        game_versions=("1.21.1",),
        loaders=("fabric",),
        files=(
            ModrinthFile(
                url="https://cdn.modrinth.com/preview.mrpack",
                filename="preview.mrpack",
                sha1="a",
                sha512="b",
                size=1,
                primary=True,
            ),
        ),
        date_published="2026-02-01T00:00:00Z",
    )
    project = ModrinthProject(
        project_id="pack",
        slug="pack",
        title="Preview Pack",
        description="",
        project_type="modpack",
    )

    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda _instance: False)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda *args, **kwargs: project)
    monkeypatch.setattr(ModrinthClient, "get_version", lambda *args, **kwargs: target)
    monkeypatch.setattr(
        ModrinthDownloader,
        "download_file",
        lambda _file, destination, **_kwargs: destination.parent.mkdir(parents=True, exist_ok=True)
        or shutil.copy2(pack_source, destination),
    )

    plan = ModrinthPackUpdateManager.preview(
        instance,
        target_version_id="v2",
        allowed_version_types=("release",),
    )

    assert plan.can_apply
    assert plan.added_files == 1
    assert plan.replaced_files == 0
    assert plan.removed_files == 1
    assert plan.preserved_files == ("config/user.cfg",)
    assert plan.unchanged_files == 1
    assert plan.estimated_download_bytes == len(new_bytes)
    assert (instance_dir / "config" / "user.cfg").read_bytes() == b"USER"
    assert (instance_dir / "mods" / "remove.jar").read_bytes() == b"REMOVE"
    assert not (instance_dir / "mods" / "new.jar").exists()
    assert tuple(Paths.modrinth_staging_root().iterdir()) == ()
