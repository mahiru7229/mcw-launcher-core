from hashlib import sha1
from types import SimpleNamespace

from src.core.curseforge.curseforge_manual_installer import CurseForgeManualInstaller
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.instance.instance import Instance


def test_manual_import_updates_managed_modpack_entry(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    source = tmp_path / "browser-download.jar"
    content = b"manual curseforge file"
    source.write_bytes(content)
    digest = sha1(content, usedforsecurity=False).hexdigest()

    CurseForgePackRegistry.save(
        instance,
        {
            "managedFiles": [
                {
                    "projectId": 10,
                    "fileId": 20,
                    "fileName": "expected.jar",
                    "path": "mods/expected.jar",
                    "displayName": "Example Mod",
                    "sha1": digest,
                    "size": len(content),
                    "pendingDownload": True,
                    "lastDownloadError": "Manual download required",
                    "retryableDownload": False,
                }
            ],
            "lastDownloadFailures": [{"projectId": 10, "fileId": 20, "path": "mods/expected.jar"}],
        },
    )

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))
    monkeypatch.setattr(ModManager, "read_mod", staticmethod(lambda *args, **kwargs: SimpleNamespace()))
    monkeypatch.setattr(ModManager, "compatibility_warning", staticmethod(lambda *args, **kwargs: "Loader metadata is unverified."))

    requirement = CurseForgeManualDownload(
        project_id=10,
        file_id=20,
        project_name="Example Mod",
        file_name="expected.jar",
        file_size=len(content),
        sha1=digest,
        project_url="https://www.curseforge.com/minecraft/mc-mods/example/files/20",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="mods/expected.jar",
    )

    installed_name = CurseForgeManualInstaller.install(instance, requirement, source)

    assert installed_name == "expected.jar"
    assert (instance_dir / "mods" / "expected.jar").read_bytes() == content
    pack = CurseForgePackRegistry.load(instance)
    entry = pack["managedFiles"][0]
    assert entry["fileName"] == "expected.jar"
    assert entry["path"] == "mods/expected.jar"
    assert entry["pendingDownload"] is False
    assert entry["retryableDownload"] is True
    assert entry["manualImport"] is True
    assert entry["acceptedUnverified"] is True
    assert pack["lastDownloadFailures"] == []


def test_manual_batch_matches_required_file_by_sha1_and_adds_extra_mod(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    required_source = tmp_path / "renamed-by-browser.jar"
    required_content = b"required curseforge content"
    required_source.write_bytes(required_content)
    extra_source = tmp_path / "extra-user-mod.jar"
    extra_source.write_bytes(b"extra mod content")
    required_digest = sha1(required_content, usedforsecurity=False).hexdigest()

    requirement = CurseForgeManualDownload(
        project_id=10,
        file_id=20,
        project_name="Example Mod",
        file_name="expected.jar",
        file_size=len(required_content),
        sha1=required_digest,
        project_url="https://www.curseforge.com/minecraft/mc-mods/example/files/20",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="mods/expected.jar",
    )

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))
    imported: list[tuple[object, object]] = []

    def fake_install(_instance, matched_requirement, source):
        imported.append((matched_requirement, source))
        return "installed-required.jar"

    def fake_add_mods(_instance, paths, replace=False, allow_unverified=False):
        assert replace is False
        assert allow_unverified is True
        source = list(paths)[0]
        return [SimpleNamespace(file_name=source.name)]

    monkeypatch.setattr(CurseForgeManualInstaller, "install", staticmethod(fake_install))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(fake_add_mods))
    monkeypatch.setattr("src.core.curseforge.curseforge_manual_installer.ModrinthRegistry.remove_by_filenames", staticmethod(lambda *_args: ()))
    monkeypatch.setattr(CurseForgeRegistry, "remove_by_filenames", staticmethod(lambda *_args: ()))

    result = CurseForgeManualInstaller.install_many(instance, [requirement], [required_source, extra_source])

    assert imported == [(requirement, required_source)]
    assert len(result.imported) == 1
    assert result.imported[0].requirement == requirement
    assert result.imported[0].installed_name == "installed-required.jar"
    assert result.added_mods == ("extra-user-mod.jar",)
    assert result.rejected == ()


def test_manual_batch_rejects_wrong_checksum_with_expected_filename(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    source = tmp_path / "expected.jar"
    source.write_bytes(b"wrong content")

    requirement = CurseForgeManualDownload(
        project_id=10,
        file_id=20,
        project_name="Example Mod",
        file_name="expected.jar",
        file_size=len(b"correct content"),
        sha1=sha1(b"correct content", usedforsecurity=False).hexdigest(),
        project_url="https://www.curseforge.com/minecraft/mc-mods/example/files/20",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="mods/expected.jar",
    )

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("wrong file must not be added"))))

    result = CurseForgeManualInstaller.install_many(instance, [requirement], [source])

    assert result.imported == ()
    assert result.added_mods == ()
    assert len(result.rejected) == 1
    assert "size or SHA-1 checksum is different" in result.rejected[0]


def test_manual_batch_imports_non_jar_managed_file_with_matching_extension(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    source = tmp_path / "ocd 1.18 (1).zip"
    content = b"resource pack archive"
    source.write_bytes(content)
    digest = sha1(content, usedforsecurity=False).hexdigest()

    CurseForgePackRegistry.save(
        instance,
        {
            "managedFiles": [
                {
                    "projectId": 30,
                    "fileId": 40,
                    "fileName": "ocd 1.18.zip",
                    "path": "resourcepacks/ocd 1.18.zip",
                    "displayName": "Original-style oCd pack",
                    "sha1": digest,
                    "size": len(content),
                    "pendingDownload": True,
                    "lastDownloadError": "Manual download required",
                    "retryableDownload": False,
                }
            ]
        },
    )

    requirement = CurseForgeManualDownload(
        project_id=30,
        file_id=40,
        project_name="Original-style oCd pack",
        file_name="ocd 1.18.zip",
        file_size=len(content),
        sha1=digest,
        project_url="https://www.curseforge.com/minecraft/texture-packs/ocd/files/40",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="resourcepacks/ocd 1.18.zip",
    )

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))

    result = CurseForgeManualInstaller.install_many(instance, [requirement], [source])

    assert len(result.imported) == 1
    assert result.imported[0].installed_name == "ocd 1.18.zip"
    assert result.added_mods == ()
    assert result.rejected == ()
    assert (instance_dir / "resourcepacks" / "ocd 1.18.zip").read_bytes() == content
    entry = CurseForgePackRegistry.load(instance)["managedFiles"][0]
    assert entry["path"] == "resourcepacks/ocd 1.18.zip"
    assert entry["pendingDownload"] is False
    assert entry["manualImport"] is True


def test_manual_batch_accepts_matching_hash_with_different_extension_and_renames(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    content = b"expected archive"
    source = tmp_path / "renamed.jar"
    source.write_bytes(content)
    CurseForgePackRegistry.save(instance, {"managedFiles": [{"projectId": 30, "fileId": 40, "fileName": "archive.zip", "path": "resourcepacks/archive.zip", "sha1": sha1(content, usedforsecurity=False).hexdigest(), "size": len(content)}]})

    requirement = CurseForgeManualDownload(
        project_id=30,
        file_id=40,
        project_name="Archive",
        file_name="archive.zip",
        file_size=len(content),
        sha1=sha1(content, usedforsecurity=False).hexdigest(),
        project_url="https://www.curseforge.com/minecraft/texture-packs/archive/files/40",
        reason="Manual download required",
        managed_kind="pack",
        managed_path="resourcepacks/archive.zip",
    )

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("managed artifact must not be added as a standalone mod"))))

    result = CurseForgeManualInstaller.install_many(instance, [requirement], [source])

    assert len(result.imported) == 1
    assert result.imported[0].installed_name == "archive.zip"
    assert result.added_mods == ()
    assert result.rejected == ()
    assert (instance_dir / "resourcepacks" / "archive.zip").read_bytes() == content
