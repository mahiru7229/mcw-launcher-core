from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile
import hashlib
import json

import pytest

from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.package.modpack_package_manager import ModpackPackageManager
from src.core.package.provider_package_store import ProviderPackageStore
from src.models.package.modpack_export import ModpackExportOptions
from src.models.package.provider_modpack_preview import ProviderModpackPreview
from src.core.progress.progress_reporter import ProgressReporter


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"portable-icon"

def write_mrpack(path: Path) -> None:
    index = {
        "formatVersion": 1,
        "game": "minecraft",
        "name": "Local Modrinth Pack",
        "versionId": "1.2.3",
        "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.10"},
        "files": [
            {
                "path": "mods/example.jar",
                "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
                "downloads": ["https://cdn.modrinth.com/data/project/versions/version/example.jar"],
                "fileSize": 123,
            }
        ],
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("modrinth.index.json", json.dumps(index))
        archive.writestr("overrides/config/example.txt", "ok")


def write_curseforge(path: Path) -> None:
    manifest = {
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": "Local CurseForge Pack",
        "version": "2.0",
        "author": "Tester",
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [{"id": "forge-47.3.0", "primary": True}],
        },
        "files": [{"projectID": 1234, "fileID": 5678, "required": True}],
        "overrides": "overrides",
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("overrides/config/example.txt", "ok")


def fake_instance(root: Path) -> SimpleNamespace:
    root.mkdir(parents=True)
    return SimpleNamespace(
        name="Portable Test",
        version_id="1.21.1",
        mod_loader=("fabric", "0.16.10"),
        icon="grass_block",
        instance_dir=root,
    )


def test_inspect_detects_modrinth_by_archive_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "renamed.zip"
    write_mrpack(package)
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.is_instance_exist", lambda _name: False)

    preview = ModpackPackageManager.inspect(package)

    assert preview.provider == "modrinth"
    assert preview.package_format == "mrpack"
    assert preview.minecraft_version == "1.21.1"
    assert preview.mod_loader == ("fabric", "0.16.10")
    assert preview.file_count == 1


def test_inspect_detects_curseforge_manifest_without_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "pack.zip"
    write_curseforge(package)
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.is_instance_exist", lambda _name: False)

    preview = ModpackPackageManager.inspect(package)

    assert preview.provider == "curseforge"
    assert preview.package_format == "curseforge_zip"
    assert preview.minecraft_version == "1.20.1"
    assert preview.mod_loader == ("forge", "47.3.0")
    assert preview.file_count == 1


def test_inspect_rejects_traversal_even_when_manifest_is_valid(tmp_path: Path) -> None:
    package = tmp_path / "unsafe.mrpack"
    write_mrpack(package)
    with ZipFile(package, "a") as archive:
        archive.writestr("../outside.txt", "no")

    with pytest.raises(RuntimeError, match="Unsafe path"):
        ModpackPackageManager.inspect(package)


def test_provider_profile_preserves_native_package_and_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "instance")
    native = tmp_path / "original.mrpack"
    write_mrpack(native)
    monkeypatch.setattr(ModpackPackageManager, "_provider_origin", lambda _instance: {
        "provider": "modrinth",
        "projectId": "project",
        "versionId": "version",
        "packName": "Original Pack",
        "packVersion": "1.2.3",
    })
    monkeypatch.setattr(ProviderPackageStore, "native_package", lambda _instance: native)
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {})
    output = tmp_path / "profile.zip"

    result = ModpackPackageManager.export(instance, output, ModpackExportOptions(mode="provider_profile"))

    assert result.native_package_included is True
    with ZipFile(output) as archive:
        profile = json.loads(archive.read("mcw-profile.json"))
        assert profile["provider"] == "modrinth"
        assert profile["providerReference"] == {"projectId": "project", "versionId": "version"}
        assert profile["nativePackageSha256"] == hashlib.sha256(native.read_bytes()).hexdigest()
        assert archive.read(profile["nativePackage"]) == native.read_bytes()
        assert json.loads(archive.read("mcw/instance-settings.json"))["java"]["path"] == ""


def test_provider_profile_exports_custom_instance_icon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "instance")
    icon = instance.instance_dir / ".mcw" / "instance-icon.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(PNG_BYTES)
    instance.icon = ".mcw/instance-icon.png"
    native = tmp_path / "original.mrpack"
    write_mrpack(native)
    monkeypatch.setattr(ModpackPackageManager, "_provider_origin", lambda _instance: {
        "provider": "modrinth",
        "projectId": "project",
        "versionId": "version",
    })
    monkeypatch.setattr(ProviderPackageStore, "native_package", lambda _instance: native)
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {})

    output = ModpackPackageManager.export(instance, tmp_path / "profile-icon.zip", ModpackExportOptions(mode="provider_profile")).output_path

    with ZipFile(output) as archive:
        profile = json.loads(archive.read("mcw-profile.json"))
        icon_metadata = profile["instanceIcon"]
        assert icon_metadata["value"] == ".mcw/instance-icon.png"
        assert icon_metadata["sha256"] == hashlib.sha256(PNG_BYTES).hexdigest()
        assert archive.read(icon_metadata["member"]) == PNG_BYTES


def test_portable_export_and_import_restore_custom_instance_icon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "source-instance")
    icon = instance.instance_dir / ".mcw" / "instance-icon.png"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(PNG_BYTES)
    instance.icon = ".mcw/instance-icon.png"
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {})
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModpackPackageManager, "_portable_override_files", lambda _instance, _include_saves: [])

    output = ModpackPackageManager.export(instance, tmp_path / "icon.mcwpack", ModpackExportOptions(mode="portable", portable_mode="smart")).output_path
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("mcwpack.json"))
        icon_metadata = manifest["instance"]["icon"]
        assert archive.read(icon_metadata["member"]) == PNG_BYTES
        assert not any(name.startswith("overrides/.mcw/instance-icon") for name in archive.namelist())

    imported_dir = tmp_path / "imported-instance"
    imported_dir.mkdir()
    imported = SimpleNamespace(name="Imported Icon", instance_dir=imported_dir, icon="grass_block")
    preview = ProviderModpackPreview(
        package_path=output,
        provider="mcw",
        package_format="portable_mcwpack",
        name=imported.name,
        version_id="1.21.1",
        version_label="Portable",
        version_id_source="mcwpack.json",
        version_id_is_provider_native=False,
        minecraft_version="1.21.1",
        mod_loader=("fabric", "0.16.10"),
        file_count=0,
        settings={"java": {"path": ""}},
    )
    monkeypatch.setattr("src.core.package.modpack_package_manager.Paths.instance_staging_root", lambda: tmp_path / "staging")
    monkeypatch.setattr("src.core.package.modpack_package_manager.VersionManager.load", lambda _version: object())
    monkeypatch.setattr("src.core.package.modpack_package_manager.ModLoaderManager.resolve", lambda *_args: object())
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.create", lambda *_args: imported)
    monkeypatch.setattr("src.core.package.modpack_package_manager.SettingsManager.save_dict", lambda *_args: None)
    monkeypatch.setattr(ModpackPackageManager, "_extract_prefixed", lambda *_args: None)
    monkeypatch.setattr(ModpackPackageManager, "_extract_embedded", lambda *_args: None)
    monkeypatch.setattr(ModpackPackageManager, "_write_portable_registries", lambda *_args: None)
    monkeypatch.setattr("src.core.package.modpack_package_manager.ModProvenanceRegistry.synchronize", lambda *_args: None)
    monkeypatch.setattr("src.core.package.modpack_package_manager.ProviderPackageStore.save_origin", lambda *_args: None)
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.load", lambda _name: imported)
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.delete_instance", lambda _name: None)

    def set_icon(_name: str, source: Path, origin: dict | None = None):
        assert source.read_bytes() == PNG_BYTES
        assert origin == {"provider": "mcw-package", "package_provider": "mcw"}
        imported.icon = ".mcw/instance-icon.png"
        return imported

    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.set_icon", set_icon)

    result = ModpackPackageManager._import_portable(output, preview, preview.settings, ProgressReporter())

    assert result.icon == ".mcw/instance-icon.png"



def test_portable_export_smart_references_and_full_embeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "instance")
    mod = instance.instance_dir / "mods" / "example.jar"
    mod.parent.mkdir(parents=True)
    mod.write_bytes(b"example mod")
    sha1 = hashlib.sha1(mod.read_bytes(), usedforsecurity=False).hexdigest()
    provenance = {
        "example.jar": {
            "fileName": "example.jar",
            "path": "mods/example.jar",
            "provider": "modrinth",
            "projectId": "project",
            "versionId": "version",
            "sha1": sha1,
            "size": mod.stat().st_size,
            "downloadUrls": ["https://cdn.modrinth.com/data/project/versions/version/example.jar"],
        }
    }
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: provenance)
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModpackPackageManager, "_portable_override_files", lambda _instance, _include_saves: [])

    smart = ModpackPackageManager.export(instance, tmp_path / "smart.mcwpack", ModpackExportOptions(mode="portable", portable_mode="smart"))
    full = ModpackPackageManager.export(instance, tmp_path / "full.mcwpack", ModpackExportOptions(mode="portable", portable_mode="full"))

    assert (smart.referenced_files, smart.embedded_files, smart.manual_files) == (1, 0, 0)
    assert (full.referenced_files, full.embedded_files, full.manual_files) == (0, 1, 0)
    with ZipFile(smart.output_path) as archive:
        entry = json.loads(archive.read("mcwpack.json"))["files"][0]
        assert entry["delivery"] == "referenced"
        assert entry["sources"][0]["provider"] == "modrinth"
        assert "embedded/mods/example.jar" not in archive.namelist()
    with ZipFile(full.output_path) as archive:
        entry = json.loads(archive.read("mcwpack.json"))["files"][0]
        assert entry["delivery"] == "embedded"
        assert archive.read(entry["embeddedPath"]) == b"example mod"


def test_portable_export_includes_untracked_local_mods(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "instance")
    mod = instance.instance_dir / "mods" / "local-only.jar"
    mod.parent.mkdir(parents=True)
    mod.write_bytes(b"local mod")
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {})
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModpackPackageManager, "_portable_override_files", lambda _instance, _include_saves: [])

    smart = ModpackPackageManager.export(instance, tmp_path / "smart-local.mcwpack", ModpackExportOptions(mode="portable", portable_mode="smart"))
    full = ModpackPackageManager.export(instance, tmp_path / "full-local.mcwpack", ModpackExportOptions(mode="portable", portable_mode="full"))

    assert (smart.referenced_files, smart.embedded_files, smart.manual_files) == (0, 0, 1)
    assert (full.referenced_files, full.embedded_files, full.manual_files) == (0, 1, 0)
    with ZipFile(smart.output_path) as archive:
        entry = json.loads(archive.read("mcwpack.json"))["files"][0]
        assert entry["provider"] == "local"
        assert entry["delivery"] == "manual"
        assert entry["hashes"]["sha512"] == hashlib.sha512(b"local mod").hexdigest()
    with ZipFile(full.output_path) as archive:
        entry = json.loads(archive.read("mcwpack.json"))["files"][0]
        assert entry["delivery"] == "embedded"
        assert archive.read(entry["embeddedPath"]) == b"local mod"


def test_portable_export_preserves_disabled_mod_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = fake_instance(tmp_path / "instance")
    mod = instance.instance_dir / "mods" / "disabled.jar.disabled"
    mod.parent.mkdir(parents=True)
    mod.write_bytes(b"disabled mod")
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {
        "disabled.jar": {
            "fileName": "disabled.jar",
            "path": "mods/disabled.jar.disabled",
            "provider": "modrinth",
            "projectId": "project",
            "versionId": "version",
            "downloadUrls": ["https://cdn.modrinth.com/data/project/versions/version/disabled.jar"],
        }
    })
    monkeypatch.setattr(ModpackPackageManager, "_portable_settings", lambda _instance: {"java": {"path": ""}})
    monkeypatch.setattr(ModpackPackageManager, "_portable_override_files", lambda _instance, _include_saves: [])

    result = ModpackPackageManager.export(instance, tmp_path / "disabled.mcwpack", ModpackExportOptions(mode="portable", portable_mode="smart"))

    with ZipFile(result.output_path) as archive:
        entry = json.loads(archive.read("mcwpack.json"))["files"][0]
        assert entry["targetPath"] == "mods/disabled.jar.disabled"
        assert entry["fileName"] == "disabled.jar"
        assert entry["enabled"] is False


def test_provider_profile_rejects_modified_native_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    native = tmp_path / "native.mrpack"
    write_mrpack(native)
    profile = tmp_path / "profile.zip"
    with ZipFile(profile, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("provider/original-package.mrpack", native.read_bytes())
        archive.writestr("mcw-profile.json", json.dumps({
            "format": ModpackPackageManager.PROFILE_FORMAT,
            "formatVersion": 1,
            "provider": "modrinth",
            "instanceName": "Profile",
            "nativePackage": "provider/original-package.mrpack",
            "nativePackageSha256": "0" * 64,
        }))
    monkeypatch.setattr("src.core.package.modpack_package_manager.InstanceManager.is_instance_exist", lambda _name: False)

    with pytest.raises(RuntimeError, match="checksum"):
        ModpackPackageManager.inspect(profile)
