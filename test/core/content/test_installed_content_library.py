from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import json

import pytest

from src.core.content.content_library_preferences import ContentLibraryPreferences
from src.core.content.content_pack_manager import ContentPackManager
from src.core.content.installed_content_library import InstalledContentLibraryManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.models.instance.instance import Instance


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Instance:
    root = tmp_path / "Library"
    (root / "mods").mkdir(parents=True)
    (root / "minecraft").mkdir(parents=True)
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, _instance: False))
    return Instance(instance_id="library", name="Library", version_id="1.20.1", instance_dir=root, mod_loader=("fabric", "0.16.0"))


def write_mod(path: Path, mod_id: str, version: str = "1.0.0") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": mod_id, "name": mod_id.title(), "version": version}))
    return path


def write_resource_pack(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        archive.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": 15, "description": "Library pack"}}))
        archive.writestr("assets/library/test.txt", "ok")
    return path


def test_library_aggregates_mods_pending_manifest_and_content_packs(instance: Instance, tmp_path: Path) -> None:
    write_mod(instance.instance_dir / "mods" / "local.jar", "local")
    ModrinthPackRegistry.save(instance.instance_dir, {
        "projectId": "pack-project",
        "versionId": "pack-version",
        "name": "Test Pack",
        "versionNumber": "2.0",
        "managedFiles": [
            {
                "path": "mods/pending.jar",
                "fileName": "pending.jar",
                "source": "download",
                "provider": "modrinth",
                "projectId": "pending-project",
                "versionId": "pending-version",
                "size": 1234,
                "downloads": ["https://cdn.modrinth.com/data/pending-project/versions/pending-version/pending.jar"],
            }
        ],
    })
    ContentPackManager.import_local(instance, "resourcepack", write_resource_pack(tmp_path / "pretty.zip"))

    library = InstalledContentLibraryManager.scan(instance)

    by_type = {}
    for item in library.items:
        by_type.setdefault(item.content_type, []).append(item)
    assert {item.name for item in by_type["mod"]} == {"Local", "pending"}
    pending = next(item for item in by_type["mod"] if item.file_name == "pending.jar")
    assert pending.provider == "modrinth"
    assert pending.managed_by_modpack is True
    assert pending.status == "pending"
    assert pending.removable is False
    assert by_type["resourcepack"][0].provider == "local"
    assert by_type["modpack"][0].name == "Test Pack"
    assert library.pending_count == 2
    assert library.managed_count == 1


def test_preferences_are_applied_and_pruned(instance: Instance) -> None:
    write_mod(instance.instance_dir / "mods" / "favorite.jar", "favorite")
    first = InstalledContentLibraryManager.scan(instance)
    mod = next(item for item in first.items if item.content_type == "mod")

    assert InstalledContentLibraryManager.set_pinned(instance, [mod.item_id], True) == (mod.item_id,)
    assert InstalledContentLibraryManager.set_ignored_update(instance, [mod.item_id], True) == (mod.item_id,)
    refreshed = InstalledContentLibraryManager.scan(instance)
    refreshed_mod = next(item for item in refreshed.items if item.item_id == mod.item_id)
    assert refreshed_mod.pinned is True
    assert refreshed_mod.ignored_update is True

    (instance.instance_dir / "mods" / "favorite.jar").unlink()
    InstalledContentLibraryManager.scan(instance)
    assert ContentLibraryPreferences.load(instance) == {}


def test_batch_toggle_and_remove_only_change_supported_items(instance: Instance, tmp_path: Path) -> None:
    write_mod(instance.instance_dir / "mods" / "local.jar", "local")
    resource = ContentPackManager.import_local(instance, "resourcepack", write_resource_pack(tmp_path / "toggle.zip"))
    library = InstalledContentLibraryManager.scan(instance)
    local_mod = next(item for item in library.items if item.content_type == "mod")
    pack = next(item for item in library.items if item.content_type == "resourcepack")

    changed = InstalledContentLibraryManager.set_enabled(instance, [local_mod.item_id, pack.item_id], False)
    assert set(changed) == {local_mod.item_id, pack.item_id}
    assert (instance.instance_dir / "mods" / "local.jar.disabled").is_file()
    assert (instance.instance_dir / "resourcepacks" / ".disabled" / resource.file_name).is_file()

    refreshed = InstalledContentLibraryManager.scan(instance)
    removable_ids = [item.item_id for item in refreshed.items if item.content_type in {"mod", "resourcepack"}]
    removed = InstalledContentLibraryManager.remove(instance, removable_ids)
    assert set(removed) == set(removable_ids)
    assert not (instance.instance_dir / "mods" / "local.jar.disabled").exists()
    assert ContentPackManager.list_entries(instance, "resourcepack") == []
