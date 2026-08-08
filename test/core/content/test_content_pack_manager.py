from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json

import pytest

from src.core.content.content_pack_manager import ContentPackManager
from src.core.content.content_pack_registry import ContentPackRegistry
from src.core.instance.instance_run_lock import InstanceRunLock
from src.models.instance.instance import Instance


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Instance:
    instance_dir = tmp_path / "Content Pack Test"
    (instance_dir / "minecraft").mkdir(parents=True)
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, _instance: False))
    return Instance(instance_id="content-pack", name="Content Pack Test", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def write_resource_pack(path: Path, *, pack_format: int = 34, description: object = "Test pack", payload: bytes = b"texture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": pack_format, "description": description}}))
        archive.writestr("assets/test/textures/block/test.png", payload)
    return path


def write_shader_pack(path: Path, *, payload: bytes = b"shader") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("shaders/program/test.vsh", payload)
        archive.writestr("shaders/program/test.fsh", payload)
    return path


def test_resource_pack_validation_reads_pack_metadata(tmp_path: Path) -> None:
    source = write_resource_pack(tmp_path / "pack.zip", pack_format=42, description={"text": "Hello"})

    metadata = ContentPackManager.validate_archive(source, "resourcepack")

    assert metadata["contentType"] == "resourcepack"
    assert metadata["packFormat"] == 42
    assert metadata["packDescription"] == '{"text":"Hello"}'
    assert metadata["entries"] == 2


def test_shader_pack_requires_root_shaders_directory(tmp_path: Path) -> None:
    valid = write_shader_pack(tmp_path / "shader.zip")
    invalid = tmp_path / "invalid.zip"
    with ZipFile(invalid, "w", ZIP_DEFLATED) as archive:
        archive.writestr("nested/shaders/test.vsh", b"shader")

    assert ContentPackManager.validate_archive(valid, "shader")["contentType"] == "shader"
    with pytest.raises(RuntimeError, match="shaders directory"):
        ContentPackManager.validate_archive(invalid, "shader")


def test_archive_validation_rejects_traversal(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.zip"
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        archive.writestr("pack.mcmeta", json.dumps({"pack": {"pack_format": 34, "description": "Unsafe"}}))
        archive.writestr("../outside.txt", b"nope")

    with pytest.raises(RuntimeError, match="Unsafe content archive path"):
        ContentPackManager.validate_archive(source, "resourcepack")


def test_local_resource_pack_lifecycle_persists_metadata(instance: Instance, tmp_path: Path) -> None:
    source = write_resource_pack(tmp_path / "source" / "pretty.zip", pack_format=34, description="Pretty")

    result = ContentPackManager.import_local(instance, "resourcepack", source)
    entries = ContentPackManager.list_entries(instance, "resourcepack")

    assert result.file_name == "pretty.zip"
    assert result.replaced is False
    assert (instance.instance_dir / "resourcepacks" / "pretty.zip").is_file()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider == "local"
    assert entry.pack_format == 34
    assert entry.pack_description == "Pretty"
    assert len(entry.sha1) == 40
    assert len(entry.sha512) == 128
    assert entry.target_path == "resourcepacks/pretty.zip"

    disabled = ContentPackManager.set_enabled(instance, entry.entry_id, False)
    assert disabled.enabled is False
    assert (instance.instance_dir / "resourcepacks" / ".disabled" / "pretty.zip").is_file()
    assert not (instance.instance_dir / "resourcepacks" / "pretty.zip").exists()

    enabled = ContentPackManager.set_enabled(instance, entry.entry_id, True)
    assert enabled.enabled is True
    assert (instance.instance_dir / "resourcepacks" / "pretty.zip").is_file()

    removed = ContentPackManager.remove(instance, entry.entry_id)
    assert removed.entry_id == entry.entry_id
    assert ContentPackManager.list_entries(instance, "resourcepack") == []
    assert not (instance.instance_dir / "resourcepacks" / "pretty.zip").exists()


def test_same_file_name_never_overwrites_unrelated_local_pack(instance: Instance, tmp_path: Path) -> None:
    first = write_resource_pack(tmp_path / "first" / "same.zip", payload=b"first")
    second = write_resource_pack(tmp_path / "second" / "same.zip", payload=b"second")

    first_result = ContentPackManager.import_local(instance, "resourcepack", first)
    second_result = ContentPackManager.import_local(instance, "resourcepack", second)

    assert first_result.file_name == "same.zip"
    assert second_result.file_name == "same (2).zip"
    entries = ContentPackManager.list_entries(instance, "resourcepack")
    assert len(entries) == 2
    assert {entry.file_name for entry in entries} == {"same.zip", "same (2).zip"}


def test_provider_project_update_replaces_old_binary(instance: Instance, tmp_path: Path) -> None:
    first = write_resource_pack(tmp_path / "project-v1.zip", payload=b"first")
    second = write_resource_pack(tmp_path / "project-v2.zip", payload=b"second")

    first_result = ContentPackManager._install_verified_file(instance, "resourcepack", first, "modrinth", "project", "version-1", "first", "Project", "1.0", "", "", 0, "", "https://modrinth.com/resourcepack/project")
    second_result = ContentPackManager._install_verified_file(instance, "resourcepack", second, "modrinth", "project", "version-2", "second", "Project", "2.0", "", "", 0, "", "https://modrinth.com/resourcepack/project")

    assert first_result.replaced is False
    assert second_result.replaced is True
    assert not (instance.instance_dir / "resourcepacks" / "project-v1.zip").exists()
    assert (instance.instance_dir / "resourcepacks" / "project-v2.zip").is_file()
    entries = ContentPackManager.list_entries(instance, "resourcepack")
    assert len(entries) == 1
    assert entries[0].version_id == "version-2"
    assert entries[0].version_number == "2.0"


def test_toggle_registry_failure_rolls_back_file_move(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_resource_pack(tmp_path / "toggle.zip")
    result = ContentPackManager.import_local(instance, "resourcepack", source)
    entry = ContentPackManager.list_entries(instance, "resourcepack")[0]
    active = instance.instance_dir / "resourcepacks" / result.file_name
    disabled = instance.instance_dir / "resourcepacks" / ".disabled" / result.file_name

    monkeypatch.setattr(ContentPackRegistry, "upsert", classmethod(lambda cls, _instance, _entry: (_ for _ in ()).throw(OSError("registry failed"))))

    with pytest.raises(OSError, match="registry failed"):
        ContentPackManager.set_enabled(instance, entry.entry_id, False)

    assert active.is_file()
    assert not disabled.exists()


def test_toggle_does_not_overwrite_destination_collision(instance: Instance, tmp_path: Path) -> None:
    source = write_resource_pack(tmp_path / "collision.zip")
    result = ContentPackManager.import_local(instance, "resourcepack", source)
    entry = ContentPackManager.list_entries(instance, "resourcepack")[0]
    disabled = instance.instance_dir / "resourcepacks" / ".disabled" / result.file_name
    write_resource_pack(disabled, payload=b"unrelated")

    with pytest.raises(RuntimeError, match="already exists"):
        ContentPackManager.set_enabled(instance, entry.entry_id, False)

    assert (instance.instance_dir / "resourcepacks" / result.file_name).is_file()
    assert disabled.is_file()


def test_registry_failure_rolls_back_new_file(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_shader_pack(tmp_path / "rollback.zip")

    monkeypatch.setattr(ContentPackRegistry, "upsert", classmethod(lambda cls, _instance, _entry: (_ for _ in ()).throw(OSError("registry failed"))))

    with pytest.raises(OSError, match="registry failed"):
        ContentPackManager.import_local(instance, "shader", source)

    assert not (instance.instance_dir / "shaderpacks" / "rollback.zip").exists()
    assert not list((instance.instance_dir / "shaderpacks").glob("*.installing.zip"))


def test_existing_content_files_are_discovered_without_reimport(instance: Instance) -> None:
    active = write_resource_pack(instance.instance_dir / "resourcepacks" / "manual.zip", pack_format=35)
    disabled = write_shader_pack(instance.instance_dir / "shaderpacks" / ".disabled" / "manual-shader.zip")

    resource_entries = ContentPackManager.list_entries(instance, "resourcepack")
    shader_entries = ContentPackManager.list_entries(instance, "shader")

    assert active.is_file()
    assert disabled.is_file()
    assert len(resource_entries) == 1
    assert resource_entries[0].provider == "local"
    assert resource_entries[0].enabled is True
    assert resource_entries[0].pack_format == 35
    assert len(shader_entries) == 1
    assert shader_entries[0].enabled is False
    assert shader_entries[0].target_path.endswith("shaderpacks/.disabled/manual-shader.zip")


def test_content_paths_and_urls_are_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr("src.core.content.content_pack_manager.Paths.CACHE_ROOT", cache_root)

    cache_path = ContentPackManager._cache_path("modrinth", "resourcepack", "../../project", "../version", "..\\unsafe.zip")

    assert cache_path.is_relative_to(cache_root)
    assert cache_path.name == "unsafe.zip"
    assert ContentPackManager._safe_file_name("CON.zip") == "_CON.zip"
    assert ContentPackManager._safe_https_url("https://cdn.example/file.zip?token=secret#fragment") == "https://cdn.example/file.zip"
    assert ContentPackManager._safe_https_url("https://user:secret@cdn.example/file.zip") == ""
    assert ContentPackManager._safe_https_url("http://cdn.example/file.zip") == ""


def test_migrates_v100_content_paths_without_overwriting_conflicts(instance: Instance) -> None:
    legacy_active = write_resource_pack(instance.instance_dir / "minecraft" / "resourcepacks" / "legacy.zip", payload=b"legacy")
    legacy_disabled = write_resource_pack(instance.instance_dir / "minecraft" / "resourcepacks" / ".disabled" / "disabled.zip", payload=b"disabled")
    conflict = write_resource_pack(instance.instance_dir / "resourcepacks" / "conflict.zip", payload=b"new")
    legacy_conflict = write_resource_pack(instance.instance_dir / "minecraft" / "resourcepacks" / "conflict.zip", payload=b"old")

    result = ContentPackManager.migrate_legacy_location(instance, "resourcepack")

    assert set(result["moved"]) == {"legacy.zip", ".disabled/disabled.zip"}
    assert result["skipped"] == ("conflict.zip",)
    assert not legacy_active.exists()
    assert not legacy_disabled.exists()
    assert (instance.instance_dir / "resourcepacks" / "legacy.zip").is_file()
    assert (instance.instance_dir / "resourcepacks" / ".disabled" / "disabled.zip").is_file()
    assert conflict.read_bytes() != legacy_conflict.read_bytes()
    assert legacy_conflict.is_file()


def test_migration_normalizes_legacy_registry_target(instance: Instance, tmp_path: Path) -> None:
    source = write_shader_pack(tmp_path / "registry.zip")
    ContentPackManager.import_local(instance, "shader", source)
    entry = ContentPackRegistry.entries(instance, "shader")[0]
    from dataclasses import replace

    ContentPackRegistry.upsert(instance, replace(entry, target_path="minecraft/shaderpacks/registry.zip"))

    result = ContentPackManager.migrate_legacy_location(instance, "shader")
    updated = ContentPackRegistry.entries(instance, "shader")[0]

    assert result["updatedRegistryEntries"] == 1
    assert updated.target_path == "shaderpacks/registry.zip"


def test_new_pack_can_be_added_while_minecraft_is_running(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_resource_pack(tmp_path / "while-running.zip")
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, _instance: True))

    result = ContentPackManager.import_local(instance, "resourcepack", source)

    assert result.file_name == "while-running.zip"
    assert (instance.instance_dir / "resourcepacks" / "while-running.zip").is_file()


def test_destructive_pack_changes_are_blocked_while_running(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_shader_pack(tmp_path / "active.zip")
    ContentPackManager.import_local(instance, "shader", source)
    entry = ContentPackRegistry.entries(instance, "shader")[0]
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, _instance: True))

    with pytest.raises(RuntimeError, match="currently be in use"):
        ContentPackManager.set_enabled(instance, entry.entry_id, False)
    with pytest.raises(RuntimeError, match="currently be in use"):
        ContentPackManager.remove(instance, entry.entry_id)


def test_provider_replacement_is_blocked_while_running(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = write_resource_pack(tmp_path / "provider-v1.zip", payload=b"one")
    second = write_resource_pack(tmp_path / "provider-v2.zip", payload=b"two")
    ContentPackManager._install_verified_file(instance, "resourcepack", first, "modrinth", "project", "v1", "one", "Pack", "1", "", "", 0, "", "")
    monkeypatch.setattr(InstanceRunLock, "is_active", classmethod(lambda cls, _instance: True))

    with pytest.raises(RuntimeError, match="cannot be replaced"):
        ContentPackManager._install_verified_file(instance, "resourcepack", second, "modrinth", "project", "v2", "two", "Pack", "2", "", "", 0, "", "")


def test_provider_content_pack_uses_shared_content_store(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr("src.core.storage.content_store.Paths.CACHE_ROOT", cache_root)
    source = write_resource_pack(tmp_path / "provider-cache" / "managed.zip", payload=b"managed-provider")

    result = ContentPackManager._install_verified_file(instance, "resourcepack", source, "modrinth", "project", "version", "file", "Managed", "1.0", "", "", 0, "", "")

    destination = instance.instance_dir / "resourcepacks" / result.file_name
    blobs = list((cache_root / "content-store" / "sha256").rglob("*"))
    blob_files = [path for path in blobs if path.is_file()]
    assert len(blob_files) == 1
    assert destination.read_bytes() == source.read_bytes()
    assert blob_files[0].read_bytes() == source.read_bytes()


def test_local_content_pack_does_not_enter_shared_content_store(instance: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setattr("src.core.storage.content_store.Paths.CACHE_ROOT", cache_root)
    source = write_resource_pack(tmp_path / "local.zip", payload=b"local-user-file")

    ContentPackManager.import_local(instance, "resourcepack", source)

    assert not (cache_root / "content-store").exists()
