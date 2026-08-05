from pathlib import Path
import json
import zipfile

from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path, name: str = "Pack") -> Instance:
    root = tmp_path / name
    root.mkdir()
    return Instance(instance_id=name.casefold(), name=name, version_id="1.20.1", instance_dir=root, mod_loader=("fabric", "0.16.0"))


def make_mod(path: Path, mod_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schemaVersion": 1, "id": mod_id, "name": mod_id.title(), "version": "1.0.0"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(payload))
    return path


def test_modrinth_pack_mod_keeps_provider_and_remote_identity(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "Modrinth")
    make_mod(instance.instance_dir / "mods" / "example.jar", "example")
    ModrinthPackRegistry.save(instance.instance_dir, {
        "projectId": "pack-project",
        "versionId": "pack-version",
        "managedFiles": [{
            "path": "mods/example.jar",
            "fileName": "example.jar",
            "source": "download",
            "provider": "modrinth",
            "downloads": ["https://cdn.modrinth.com/data/mod-project/versions/mod-version/example.jar"],
        }],
    })

    mods = ModManager.list_mods(instance)
    entry = ModProvenanceRegistry.entry_for_file(instance, "example.jar")

    assert mods[0].source == "modrinth"
    assert mods[0].managed_by_modpack is True
    assert mods[0].source_project_id == "mod-project"
    assert mods[0].source_version_id == "mod-version"
    assert entry is not None
    assert entry["packProvider"] == "modrinth"
    assert entry["packProjectId"] == "pack-project"


def test_curseforge_pack_mod_keeps_project_and_file_ids(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "CurseForge")
    make_mod(instance.instance_dir / "mods" / "cf-example.jar", "cf_example")
    CurseForgePackRegistry.save(instance, {
        "projectId": 500,
        "fileId": 600,
        "managedFiles": [{
            "projectId": 123,
            "fileId": 456,
            "fileName": "cf-example.jar",
            "path": "mods/cf-example.jar",
            "displayName": "CF Example 1.0",
        }],
    })

    mod = ModManager.list_mods(instance)[0]

    assert mod.source == "curseforge"
    assert mod.managed_by_modpack is True
    assert mod.source_project_id == "123"
    assert mod.source_file_id == "456"
    assert mod.source_pack_provider == "curseforge"


def test_ftb_pack_mod_is_marked_as_ftb(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "FTB")
    make_mod(instance.instance_dir / "mods" / "ftb-example.jar", "ftb_example")
    FTBPackRegistry.save(instance, {
        "projectId": 25,
        "versionId": 101,
        "managedFiles": [{
            "fileId": 777,
            "fileName": "ftb-example.jar",
            "path": "mods/ftb-example.jar",
            "urls": ["https://example.invalid/ftb-example.jar"],
        }],
    })

    mod = ModManager.list_mods(instance)[0]

    assert mod.source == "ftb"
    assert mod.managed_by_modpack is True
    assert mod.source_file_id == "777"


def test_untracked_mod_remains_local(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "Local")
    make_mod(instance.instance_dir / "mods" / "local.jar", "local")

    mod = ModManager.list_mods(instance)[0]

    assert mod.source == "local"
    assert mod.managed_by_modpack is False
