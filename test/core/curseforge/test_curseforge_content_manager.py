from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.curseforge.curseforge_content_manager import CurseForgeContentManager
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader
from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.fs.paths import Paths
from src.core.mod.mod_manager import ModManager
from src.models.curseforge.file import CurseForgeFile
from src.models.instance.instance import Instance


def test_download_round_forwards_launch_lock_token_to_managed_mod_install(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    cache_path = tmp_path / "cache" / "example.jar"
    received = {}
    file = CurseForgeFile(
        file_id=2,
        project_id=1,
        display_name="Example",
        file_name="example.jar",
        release_type="release",
        file_date="",
        file_length=3,
        download_url="https://example.invalid/example.jar",
        sha1="a" * 40,
        game_versions=("1.18.2",),
        dependencies=(),
        loaders=("forge",),
    )

    monkeypatch.setattr(CurseForgeClient, "get_file", staticmethod(lambda *args, **kwargs: file))
    monkeypatch.setattr(Paths, "curseforge_file_cache", staticmethod(lambda *args: cache_path))

    def fake_download(_file, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"jar")
        return destination

    def fake_add_mods(current_instance, source_paths, replace=False, launch_lock_token=None, allow_unverified=False, managed_source=False):
        received["instance"] = current_instance
        received["paths"] = list(source_paths)
        received["replace"] = replace
        received["token"] = launch_lock_token
        received["allow_unverified"] = allow_unverified
        received["managed_source"] = managed_source
        return [SimpleNamespace(file_name="example.jar")]

    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(fake_download))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(fake_add_mods))

    entry = {
        "projectId": 1,
        "fileId": 2,
        "fileName": "example.jar",
        "path": "mods/example.jar",
        "sha1": "",
        "size": 0,
    }
    missing = [{"kind": "mod", "key": "mod:1:2", "path": "mods/example.jar", "entry": entry}]

    result = CurseForgeContentManager._download_round(instance, missing, None, 1, "owned-token")

    assert result["errors"] == {}
    assert result["downloaded"] == 1
    assert received == {
        "instance": instance,
        "paths": [cache_path],
        "replace": True,
        "token": "owned-token",
        "allow_unverified": True,
        "managed_source": True,
    }
    assert entry["pendingDownload"] is False
    assert entry["lastDownloadError"] == ""


def test_download_round_places_manifest_managed_zip_without_mod_validation(tmp_path, monkeypatch):
    from hashlib import sha1

    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    content = b"manifest managed archive"
    digest = sha1(content, usedforsecurity=False).hexdigest()
    cache_path = tmp_path / "cache" / "archive.zip"
    file = CurseForgeFile(file_id=4, project_id=3, display_name="Archive", file_name="archive.zip", release_type="release", file_date="", file_length=len(content), download_url="https://example.invalid/archive.zip", sha1=digest, game_versions=("1.18.2",), dependencies=(), loaders=())

    monkeypatch.setattr(Paths, "curseforge_file_cache", staticmethod(lambda *args: cache_path))
    store_root = tmp_path / "content-store"
    monkeypatch.setattr(Paths, "content_store_blob", staticmethod(lambda digest: store_root / digest[:2] / digest))

    def fake_download(_file, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(fake_download))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("managed ZIP must not use ModManager"))))
    entry = {"projectId": 3, "fileId": 4, "fileName": "archive.zip", "path": "mods/archive.zip", "sha1": digest, "size": len(content), "downloadUrl": file.download_url}
    missing = [{"kind": "pack", "key": "pack:3:4", "path": "mods/archive.zip", "entry": entry}]

    result = CurseForgeContentManager._download_round(instance, missing, None, 1)

    assert result["errors"] == {}
    assert (instance_dir / "mods" / "archive.zip").read_bytes() == content
    assert entry["path"] == "mods/archive.zip"


def test_manual_download_errors_are_grouped_without_request_ids():
    first = CurseForgeContentManager._normalized_error(
        "This CurseForge file must be downloaded manually because third-party distribution is unavailable. Request ID: abcdefab-1234-1234-1234-abcdefabcdef."
    )
    second = CurseForgeContentManager._normalized_error(
        "This CurseForge file must be downloaded manually because third-party distribution is unavailable. Request ID: 01234567-89ab-cdef-0123-456789abcdef."
    )

    assert first == second
    assert "Manual download is required" in first
    assert "Request ID" not in first


def test_launch_failure_exposes_manual_import_requirements(tmp_path, monkeypatch):
    from src.core.curseforge.curseforge_content_manager import CurseForgeManagedFilesRequired
    from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry

    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Manual Pack", version_id="1.18.2", instance_dir=instance_dir, mod_loader=("forge", "40.2.0"))
    CurseForgePackRegistry.save(
        instance,
        {
            "managedFiles": [
                {
                    "projectId": 101,
                    "fileId": 202,
                    "fileName": "restricted.jar",
                    "path": "mods/restricted.jar",
                    "displayName": "Restricted Mod",
                    "sha1": "b" * 40,
                    "size": 123,
                    "pendingDownload": True,
                    "lastDownloadError": "This CurseForge file must be downloaded manually because third-party distribution is unavailable.",
                    "retryableDownload": False,
                }
            ]
        },
    )
    project = SimpleNamespace(name="Restricted Mod", project_url="https://www.curseforge.com/minecraft/mc-mods/restricted-mod")
    monkeypatch.setattr(CurseForgeClient, "get_projects_batch", staticmethod(lambda ids: {101: project}))

    with pytest.raises(CurseForgeManagedFilesRequired) as captured:
        CurseForgeContentManager.ensure(instance, block_launch_on_failure=True)

    error = captured.value
    assert error.instance_name == "Manual Pack"
    assert error.instance_dir == instance_dir
    assert len(error.requirements) == 1
    requirement = error.requirements[0]
    assert requirement.managed_kind == "pack"
    assert requirement.managed_path == "mods/restricted.jar"
    assert requirement.project_url == "https://www.curseforge.com/minecraft/mc-mods/restricted-mod"
    assert requirement.version_url == "https://www.curseforge.com/minecraft/mc-mods/restricted-mod/files/202"
    assert requirement.sha1 == "b" * 40


def test_manual_requirements_preserve_structured_failure_and_all_links(monkeypatch):
    from src.models.curseforge.manual_download import CurseForgeManualDownload

    existing = CurseForgeManualDownload(
        project_id=11,
        file_id=22,
        project_name="Example",
        file_name="example.zip",
        file_size=7,
        sha1="c" * 40,
        project_url="https://www.curseforge.com/minecraft/mc-mods/example",
        version_url="https://www.curseforge.com/minecraft/mc-mods/example/files/22",
        direct_url="https://edge.forgecdn.net/example.zip",
        reason="Automatic download failed (HTTP_404): HTTP 404.",
        failure_reason="HTTP_404",
        http_status=404,
        attempts=5,
        retryable=False,
        managed_kind="pack",
        managed_path="mods/example.zip",
    )
    entry = {"projectId": 11, "fileId": 22, "fileName": "example.zip", "path": "mods/example.zip", "sha1": "c" * 40, "size": 7}
    missing = [{"kind": "pack", "key": "pack:11:22", "path": "mods/example.zip", "entry": entry}]
    monkeypatch.setattr(CurseForgeClient, "get_projects_batch", staticmethod(lambda _ids: {}))

    requirements = CurseForgeContentManager._manual_requirements(missing, {"pack:11:22": {"message": str(existing.reason), "retryable": False, "requirement": existing}})

    requirement = requirements[0]
    assert requirement.direct_url == existing.direct_url
    assert requirement.version_url == existing.version_url
    assert requirement.project_url == existing.project_url
    assert requirement.failure_reason == "HTTP_404"
    assert requirement.http_status == 404
    assert requirement.attempts == 5


def test_download_round_reports_only_aggregate_mod_progress(tmp_path, monkeypatch):
    from src.core.progress.progress_reporter import ProgressReporter
    from src.models.progress.progress_stage import ProgressStage
    from src.models.progress.progress_unit import ProgressUnit

    instance_dir = tmp_path / "instance-progress"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.4.0"))
    cache_path = tmp_path / "cache-progress" / "example.jar"
    file = CurseForgeFile(
        file_id=2,
        project_id=1,
        display_name="Very Verbose Mod Name",
        file_name="example.jar",
        release_type="release",
        file_date="",
        file_length=3,
        download_url="https://example.invalid/example.jar",
        sha1="a" * 40,
        game_versions=("1.20.1",),
        dependencies=(),
        loaders=("forge",),
    )
    events = []

    monkeypatch.setattr(Paths, "curseforge_file_cache", staticmethod(lambda *args: cache_path))

    def fake_download(_file, destination, reporter=None, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if reporter is not None:
            reporter.bytes(ProgressStage.DOWNLOADING_MODS, "Very Verbose Mod Name", 1, 3, bytes_per_second=1_500_000)
        destination.write_bytes(b"jar")
        return destination

    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(fake_download))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(lambda *_args, **_kwargs: [SimpleNamespace(file_name="example.jar")]))
    entry = {"projectId": 1, "fileId": 2, "fileName": "example.jar", "path": "mods/example.jar", "sha1": "a" * 40, "size": 3, "downloadUrl": file.download_url}
    missing = [{"kind": "mod", "key": "mod:1:2", "path": "mods/example.jar", "entry": entry}]
    monkeypatch.setattr(ModManager, "read_mod", staticmethod(lambda *_args, **_kwargs: SimpleNamespace()))
    monkeypatch.setattr(ModManager, "compatibility_warning", staticmethod(lambda *_args, **_kwargs: ""))

    result = CurseForgeContentManager._download_round(instance, missing, ProgressReporter(events.append), 1, "token")

    assert result["errors"] == {}
    progress = [event for event in events if event.stage is ProgressStage.DOWNLOADING_MODS]
    assert progress
    assert all(event.unit is ProgressUnit.FILES for event in progress)
    assert all(event.message == "Downloading modpack mods..." for event in progress)
    assert all("Very Verbose Mod Name" not in event.message for event in progress)
    assert any((event.bytes_per_second or 0) > 0 for event in progress)


def test_manual_pack_jar_with_exact_sha1_accepts_provider_identity_when_legacy_metadata_is_unreadable(tmp_path):
    from hashlib import sha1
    import zipfile

    instance_dir = tmp_path / "instance-manual-identity"
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True)
    instance = Instance(instance_id="id", name="Legacy Pack", version_id="1.12.2", instance_dir=instance_dir, mod_loader=("forge", "14.23.5.2860"))
    target = mods_dir / "Reskillable-1.12.2-1.13.0.jar"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nFMLCorePluginContainsFMLMod: true\n")
        archive.writestr("codersafterdark/reskillable/Reskillable.class", b"legacy bytecode placeholder")
    digest = sha1(target.read_bytes(), usedforsecurity=False).hexdigest()
    entry = {
        "projectId": 286382,
        "fileId": 2815686,
        "fileName": target.name,
        "path": f"mods/{target.name}",
        "sha1": digest,
        "size": target.stat().st_size,
        "manualImport": True,
        "expectedModIds": ["reskillable"],
    }

    missing = CurseForgeContentManager._check_all(instance, [entry], [], None, 1)

    assert missing == []
    assert entry["pendingDownload"] is False
    assert entry["acceptedUnverified"] is True
    assert "Provider identity was accepted" in entry["compatibilityWarning"]


def test_verified_pack_identity_mismatch_does_not_trigger_redownload(tmp_path):
    from hashlib import sha1
    import zipfile

    instance_dir = tmp_path / "instance-non-manual-identity"
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True)
    instance = Instance(instance_id="id", name="Legacy Pack", version_id="1.12.2", instance_dir=instance_dir, mod_loader=("forge", "14.23.5.2860"))
    target = mods_dir / "legacy-unverified.jar"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
        archive.writestr("example/Legacy.class", b"legacy bytecode placeholder")
    entry = {
        "projectId": 1,
        "fileId": 2,
        "fileName": target.name,
        "path": f"mods/{target.name}",
        "sha1": sha1(target.read_bytes(), usedforsecurity=False).hexdigest(),
        "size": target.stat().st_size,
        "manualImport": False,
        "expectedModIds": ["expectedmod"],
    }

    missing = CurseForgeContentManager._check_all(instance, [entry], [], None, 1)

    assert missing == []
    assert entry["pendingDownload"] is False
    assert entry["acceptedUnverified"] is True
    assert "Provider identity was accepted" in entry["compatibilityWarning"]


def test_manual_pack_ready_forge_library_with_exact_sha1_accepts_provider_identity(tmp_path):
    from hashlib import sha1
    import zipfile

    instance_dir = tmp_path / "instance-manual-ready-library"
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True)
    instance = Instance(instance_id="id", name="Legacy Pack", version_id="1.12.2", instance_dir=instance_dir, mod_loader=("forge", "14.23.5.2860"))
    target = mods_dir / "Reskillable-1.12.2-1.13.0.jar"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\nFMLModType: LIBRARY\nImplementation-Version: 1.13.0\n",
        )
        archive.writestr("codersafterdark/reskillable/Reskillable.class", b"legacy bytecode placeholder")
    digest = sha1(target.read_bytes(), usedforsecurity=False).hexdigest()
    entry = {
        "projectId": 286382,
        "fileId": 2815686,
        "fileName": target.name,
        "path": f"mods/{target.name}",
        "sha1": digest,
        "size": target.stat().st_size,
        "manualImport": True,
        "expectedModIds": ["reskillable"],
    }

    parsed = ModManager.read_mod(target, preferred_loader="forge")
    assert parsed.status == "Ready"
    assert parsed.mod_id == "unknown"

    missing = CurseForgeContentManager._check_all(instance, [entry], [], None, 1)

    assert missing == []
    assert entry["pendingDownload"] is False
    assert entry["acceptedUnverified"] is True
    assert "Provider identity was accepted" in entry["compatibilityWarning"]


def test_exact_sha1_pack_file_with_parser_broken_jar_uses_provider_identity_without_redownload(tmp_path):
    from hashlib import sha1

    instance_dir = tmp_path / "instance-provider-broken-jar"
    mods_dir = instance_dir / "mods"
    mods_dir.mkdir(parents=True)
    instance = Instance(instance_id="id", name="Legacy Pack", version_id="1.12.2", instance_dir=instance_dir, mod_loader=("forge", "14.23.5.2860"))
    target = mods_dir / "Reskillable-1.12.2-1.13.0.jar"
    target.write_bytes(b"provider fixture whose generic ZIP parser rejects it")
    entry = {
        "projectId": 286382,
        "fileId": 2815686,
        "fileName": target.name,
        "path": f"mods/{target.name}",
        "sha1": sha1(target.read_bytes(), usedforsecurity=False).hexdigest(),
        "size": target.stat().st_size,
        "manualImport": True,
        "expectedModIds": ["reskillable"],
    }

    parsed = ModManager.read_mod(target, preferred_loader="forge")
    assert parsed.status == "Broken JAR"

    missing = CurseForgeContentManager._check_all(instance, [entry], [], None, 1)

    assert missing == []
    assert entry["pendingDownload"] is False
    assert entry["acceptedUnverified"] is True
    assert "Provider identity was accepted" in entry["compatibilityWarning"]


def test_parser_broken_jar_identity_is_not_trusted_without_verified_provider_file():
    metadata = SimpleNamespace(status="Broken JAR")
    entry = {"sha1": "a" * 40, "expectedModIds": ["reskillable"]}

    assert CurseForgeContentManager._can_trust_provider_identity(metadata, entry, provider_file_verified=False) is False
    assert CurseForgeContentManager._can_trust_provider_identity(metadata, entry, provider_file_verified=True) is True


def test_download_round_downloads_multiple_artifacts_concurrently(tmp_path, monkeypatch):
    from threading import Barrier, BrokenBarrierError, Lock

    instance_dir = tmp_path / "instance-concurrent"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.4.0"))
    barrier = Barrier(2)
    lock = Lock()
    active = 0
    peak = 0

    def cache_path(project_id, file_id, file_name):
        return tmp_path / "cache-concurrent" / f"{project_id}-{file_id}-{file_name}"

    def fake_download(_file, destination, **_kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=1)
        except BrokenBarrierError:
            pass
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"jar")
        with lock:
            active -= 1
        return destination

    monkeypatch.setattr(Paths, "curseforge_file_cache", staticmethod(cache_path))
    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(fake_download))
    monkeypatch.setattr(ModManager, "read_mod", staticmethod(lambda *_args, **_kwargs: SimpleNamespace()))
    monkeypatch.setattr(ModManager, "compatibility_warning", staticmethod(lambda *_args, **_kwargs: ""))
    monkeypatch.setattr(ModManager, "add_mods", staticmethod(lambda _instance, paths, **_kwargs: [SimpleNamespace(file_name=Path(paths[0]).name)]))

    missing = []
    for project_id in (1, 2):
        entry = {"projectId": project_id, "fileId": project_id + 10, "fileName": f"mod-{project_id}.jar", "path": f"mods/mod-{project_id}.jar", "sha1": str(project_id) * 40, "size": 3, "downloadUrl": f"https://example.invalid/mod-{project_id}.jar", "declaredLoaders": ["forge"], "gameVersions": ["1.20.1"]}
        missing.append({"kind": "mod", "key": f"mod:{project_id}:{project_id + 10}", "path": entry["path"], "entry": entry})

    result = CurseForgeContentManager._download_round(instance, missing, None, 1, "token")

    assert result["errors"] == {}
    assert result["downloaded"] == 2
    assert peak >= 2
    assert peak <= CurseForgeContentManager.MAX_WORKERS


def test_large_modpack_download_uses_lower_worker_limit_to_keep_ui_responsive():
    assert CurseForgeContentManager._download_worker_count(188) == 6
    assert CurseForgeContentManager._download_worker_count(40) == 8
    assert CurseForgeContentManager._download_worker_count(3) == 3
