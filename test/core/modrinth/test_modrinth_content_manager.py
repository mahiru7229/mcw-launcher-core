from pathlib import Path
from types import SimpleNamespace
import hashlib
import shutil

import pytest

from src.core.fs.paths import Paths
from src.core.mod.mod_manager import ModManager
from src.core.modrinth.modrinth_content_manager import ModrinthContentManager
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_errors import ModrinthManagedFilesRequired
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.network.artifact_download_service import ArtifactDownloadError
from src.core.network.download_pause import DownloadPausedError
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactDownloadFailure, DownloadFailureReason
from src.models.progress.progress_stage import ProgressStage


def make_instance(tmp_path: Path) -> Instance:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    return Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def save_pack_entry(instance: Instance, content: bytes, filename: str = "example.jar") -> None:
    ModrinthPackRegistry.save(instance.instance_dir, {
        "projectId": "pack",
        "versionId": "v1",
        "managedFiles": [{
            "path": f"mods/{filename}",
            "sha1": hashlib.sha1(content).hexdigest(),
            "sha512": hashlib.sha512(content).hexdigest(),
            "size": len(content),
            "source": "download",
            "downloads": [f"https://cdn.modrinth.com/data/pack/{filename}"],
        }],
    })


def save_mod_entry(instance: Instance, content: bytes, filename: str = "manual.jar") -> None:
    ModrinthRegistry.save(instance, {
        "mods": {
            "manual-project": {
                "projectId": "manual-project",
                "versionId": "manual-version",
                "fileName": filename,
                "sha1": hashlib.sha1(content).hexdigest(),
                "sha512": hashlib.sha512(content).hexdigest(),
                "size": len(content),
                "downloadUrls": [f"https://cdn.modrinth.com/data/manual-project/versions/manual-version/{filename}"],
                "title": "Manual Mod",
            },
        },
    })


def patch_mod_install(monkeypatch, tmp_path: Path, instance: Instance, content: bytes) -> None:
    cache_root = tmp_path / "cache"

    def fake_cache(project_id, version_id, filename):
        return cache_root / str(project_id) / str(version_id) / Path(filename).name

    def fake_add_mods(current_instance, source_paths, replace=False, managed_source=False, **_kwargs):
        source = Path(tuple(source_paths)[0])
        target = Path(current_instance.instance_dir) / "mods" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        assert managed_source is True
        shutil.copy2(source, target)
        return [SimpleNamespace(file_name=target.name)]

    monkeypatch.setattr(Paths, "modrinth_file_cache", fake_cache)
    monkeypatch.setattr(ModManager, "add_mods", fake_add_mods)


def test_missing_pack_file_downloads_once_then_only_verifies(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"fabric-mod"
    save_pack_entry(instance, content)
    calls = []

    def fake_download_urls(urls, destination, **kwargs):
        calls.append((tuple(urls), destination, kwargs["max_retry"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fake_download_urls)
    events = []
    reporter = ProgressReporter(events.append)

    assert ModrinthContentManager.ensure(instance, reporter) == ()
    assert (instance.instance_dir / "mods" / "example.jar").read_bytes() == content
    assert calls == [(("https://cdn.modrinth.com/data/pack/example.jar",), instance.instance_dir / "mods" / "example.jar", 1)]

    assert ModrinthContentManager.ensure(instance, reporter) == ()
    assert len(calls) == 1
    assert any(event.stage is ProgressStage.CHECKING_MODPACK for event in events)
    assert any(event.stage is ProgressStage.DOWNLOADING_MODS for event in events)


def test_all_modrinth_files_are_checked_before_any_download(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    pack_content = b"pack-mod"
    mod_content = b"manual-mod"
    save_pack_entry(instance, pack_content, "pack.jar")
    save_mod_entry(instance, mod_content, "manual.jar")
    patch_mod_install(monkeypatch, tmp_path, instance, mod_content)

    operations = []
    original_verify = ModrinthDownloader.verify
    original_pack_verify = ModrinthPackRegistry.verify_entry

    def tracked_pack_verify(instance_dir, entry, **kwargs):
        operations.append(("check", Path(str(entry.get("path") or "")).name))
        return original_pack_verify(instance_dir, entry, **kwargs)

    def tracked_verify(path, **kwargs):
        operations.append(("check", Path(path).name))
        return original_verify(path, **kwargs)

    def fake_download_urls(urls, destination, **kwargs):
        destination = Path(destination)
        operations.append(("download", destination.name))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(pack_content if destination.name == "pack.jar" else mod_content)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "verify", tracked_verify)
    monkeypatch.setattr(ModrinthPackRegistry, "verify_entry", tracked_pack_verify)
    monkeypatch.setattr(ModrinthDownloader, "download_urls", fake_download_urls)

    assert ModrinthContentManager.ensure(instance) == ()

    first_download = next(index for index, operation in enumerate(operations) if operation[0] == "download")
    assert operations[:first_download] == [("check", "pack.jar"), ("check", "manual.jar")]
    assert [operation for operation in operations if operation[0] == "download"] == [("download", "pack.jar"), ("download", "manual.jar")]


def test_failed_mod_is_rechecked_and_retried_in_next_round(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"manual-mod"
    save_mod_entry(instance, content)
    patch_mod_install(monkeypatch, tmp_path, instance, content)
    attempts = []
    events = []

    def flaky_download(urls, destination, **kwargs):
        attempts.append(kwargs["max_retry"])
        if len(attempts) == 1:
            raise RuntimeError("temporary CDN failure")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_urls", flaky_download)

    assert ModrinthContentManager.ensure(instance, ProgressReporter(events.append)) == ()
    assert attempts == [1, 1]
    assert (instance.instance_dir / "mods" / "manual.jar").is_file()
    checking_messages = [event.message for event in events if event.stage is ProgressStage.CHECKING_MODS]
    downloading_messages = [event.message for event in events if event.stage is ProgressStage.DOWNLOADING_MODS]
    assert any("after download round 1/3" in message for message in checking_messages)
    assert downloading_messages and all(message == "Downloading modpack mods..." for message in downloading_messages)


def test_failed_pack_file_raises_after_three_complete_rounds(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"fabric-mod"
    save_pack_entry(instance, content)
    attempts = []

    def fail_download(*args, **kwargs):
        attempts.append(kwargs["max_retry"])
        raise RuntimeError("temporary CDN failure")

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fail_download)

    with pytest.raises(ModrinthManagedFilesRequired, match="after 3 rounds") as error:
        ModrinthContentManager.ensure(instance)

    assert attempts == [1, 1, 1]
    assert "mods/example.jar" in str(error.value)
    assert len(error.value.requirements) == 1
    assert error.value.requirements[0].managed_path == "mods/example.jar"
    assert not (instance.instance_dir / "mods" / "example.jar").exists()
    registry = ModrinthPackRegistry.load(instance)
    assert registry["lastDownloadFailures"] == [{"path": "mods/example.jar", "error": "temporary CDN failure"}]


def test_existing_legacy_mod_is_verified_without_downloading(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"legacy-mod"
    target = instance.instance_dir / "mods" / "legacy.jar"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    ModrinthRegistry.save(instance, {
        "mods": {
            "legacy-project": {
                "projectId": "legacy-project",
                "versionId": "legacy-version",
                "fileName": "legacy.jar",
                "sha1": hashlib.sha1(content).hexdigest(),
                "title": "Legacy Mod",
            },
        },
    })

    def unexpected_download(*args, **kwargs):
        raise AssertionError("A valid installed mod must not be downloaded again")

    monkeypatch.setattr(ModrinthDownloader, "download_urls", unexpected_download)

    assert ModrinthContentManager.ensure(instance) == ()

def test_failed_pack_file_can_continue_for_manual_install_when_instance_option_is_disabled(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"fabric-mod"
    save_pack_entry(instance, content)
    attempts = []

    def fail_download(*args, **kwargs):
        attempts.append(kwargs["max_retry"])
        raise RuntimeError("temporary CDN failure")

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fail_download)

    warnings = ModrinthContentManager.ensure(instance, block_launch_on_failure=False)

    assert attempts == [1, 1, 1]
    assert any("Launching with 1 missing Modrinth file(s)" in warning for warning in warnings)
    assert any("mods/example.jar" in warning for warning in warnings)
    assert any("Managed modpack file checks" in warning for warning in warnings)
    registry = ModrinthPackRegistry.load(instance)
    assert registry["lastDownloadFailures"] == [{"path": "mods/example.jar", "error": "temporary CDN failure"}]


def test_failed_tracked_mod_manual_warning_contains_destination_path(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"manual-mod"
    save_mod_entry(instance, content, "manual.jar")
    patch_mod_install(monkeypatch, tmp_path, instance, content)

    monkeypatch.setattr(ModrinthDownloader, "download_urls", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("CDN unavailable")))

    warnings = ModrinthContentManager.ensure(instance, block_launch_on_failure=False)

    assert any("mods/manual.jar (Manual Mod)" in warning for warning in warnings)
    registry = ModrinthRegistry.load(instance)
    entry = registry["mods"]["manual-project"]
    assert entry["pendingDownload"] is True
    assert entry["lastDownloadError"] == "CDN unavailable"



def test_pause_is_not_swallowed_as_a_modrinth_download_failure(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    save_pack_entry(instance, b"pause-me")

    monkeypatch.setattr(ModrinthDownloader, "download_urls", lambda *args, **kwargs: (_ for _ in ()).throw(DownloadPausedError("paused")))

    with pytest.raises(DownloadPausedError):
        ModrinthContentManager.ensure(instance)


def test_missing_pack_files_download_with_adaptive_parallelism(tmp_path, monkeypatch):
    from threading import Lock
    import time

    instance = make_instance(tmp_path)
    content = b"parallel-mod"
    entries = []
    for index in range(6):
        filename = f"parallel-{index}.jar"
        entries.append({
            "path": f"mods/{filename}",
            "sha1": hashlib.sha1(content).hexdigest(),
            "sha512": hashlib.sha512(content).hexdigest(),
            "size": len(content),
            "source": "download",
            "downloads": [f"https://cdn.modrinth.com/data/pack/{filename}"],
        })
    ModrinthPackRegistry.save(instance.instance_dir, {"projectId": "pack", "versionId": "v1", "managedFiles": entries})

    lock = Lock()
    active = 0
    max_active = 0

    def fake_download_urls(urls, destination, **kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.04)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            return destination
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fake_download_urls)
    monkeypatch.setattr(ModrinthContentManager, "_download_worker_count", staticmethod(lambda _total: 3))

    assert ModrinthContentManager.ensure(instance) == ()
    assert max_active == 3
    assert max_active <= ModrinthContentManager.MAX_DOWNLOAD_WORKERS


def test_download_worker_count_is_conservative_on_low_core_systems(monkeypatch):
    monkeypatch.setattr("src.core.modrinth.modrinth_content_manager.cpu_count", lambda: 4)
    monkeypatch.setattr("src.core.modrinth.modrinth_content_manager.download_manager._global_limit", 8)

    assert ModrinthContentManager._download_worker_count(20) == 2


def test_missing_pack_artifact_without_url_exposes_no_download_url_manual_fallback(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"manual zip"
    ModrinthPackRegistry.save(instance.instance_dir, {
        "projectId": "pack-project",
        "versionId": "pack-version",
        "name": "Manual Pack",
        "managedFiles": [{
            "path": "mods/manual.zip",
            "sha1": hashlib.sha1(content).hexdigest(),
            "sha512": hashlib.sha512(content).hexdigest(),
            "size": len(content),
            "source": "download",
            "downloads": [],
        }],
    })
    monkeypatch.setattr(ModrinthContentManager, "_hydrate_pack_downloads", staticmethod(lambda *_args, **_kwargs: None))

    with pytest.raises(ModrinthManagedFilesRequired) as captured:
        ModrinthContentManager.ensure(instance)

    requirement = captured.value.requirements[0]
    assert requirement.file_name == "manual.zip"
    assert requirement.managed_path == "mods/manual.zip"
    assert requirement.failure_reason == "NO_DOWNLOAD_URL"
    assert requirement.direct_url == ""
    assert requirement.version_url.endswith("/version/pack-version")


def test_expected_dependency_mod_id_blocks_wrong_provider_file(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"provider-file"
    save_mod_entry(instance, content, "dependency.jar")
    registry = ModrinthRegistry.load(instance)
    registry["mods"]["manual-project"]["expectedModId"] = "kotlinforforge"
    ModrinthRegistry.save(instance, registry)

    cache = tmp_path / "cache" / "dependency.jar"
    monkeypatch.setattr(Paths, "modrinth_file_cache", lambda *_args: cache)

    def fake_download(urls, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fake_download)
    monkeypatch.setattr(ModManager, "read_mod", lambda *_args, **_kwargs: SimpleNamespace(mod_id="wrong_mod"))
    monkeypatch.setattr(ModManager, "add_mods", lambda *_args, **_kwargs: pytest.fail("wrong dependency must not be installed"))

    warnings = ModrinthContentManager.ensure(instance, block_launch_on_failure=False)

    assert any("requires 'kotlinforforge'" in warning for warning in warnings)
    saved = ModrinthRegistry.load(instance)["mods"]["manual-project"]
    assert saved["pendingDownload"] is True
    assert "provides mod ID 'wrong_mod'" in saved["lastDownloadError"]


def test_expected_dependency_mod_id_accepts_forge_jarjar_provided_mod(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    content = b"provider-file"
    save_mod_entry(instance, content, "kotlinforforge-3.9.1-all.jar")
    registry = ModrinthRegistry.load(instance)
    registry["mods"]["manual-project"]["expectedModId"] = "kotlinforforge"
    ModrinthRegistry.save(instance, registry)

    cache = tmp_path / "cache" / "kotlinforforge-3.9.1-all.jar"
    monkeypatch.setattr(Paths, "modrinth_file_cache", lambda *_args: cache)

    def fake_download(urls, destination, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    def fake_add_mods(current_instance, source_paths, **_kwargs):
        source = next(iter(source_paths))
        target = current_instance.instance_dir / "mods" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return [SimpleNamespace(file_name=target.name)]

    monkeypatch.setattr(ModrinthDownloader, "download_urls", fake_download)
    monkeypatch.setattr(ModManager, "read_mod", lambda *_args, **_kwargs: SimpleNamespace(mod_id="unknown", provided_mods=(("kotlinforforge", "3.9.1"),)))
    monkeypatch.setattr(ModManager, "add_mods", fake_add_mods)

    assert ModrinthContentManager.ensure(instance) == ()
    saved = ModrinthRegistry.load(instance)["mods"]["manual-project"]
    assert saved["pendingDownload"] is False
    assert saved["lastDownloadError"] == ""


def test_disk_full_aborts_modrinth_content_without_manual_pause(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    save_pack_entry(instance, b"fabric-mod")
    failure = ArtifactDownloadFailure(
        provider="modrinth",
        filename="example.jar",
        reason=DownloadFailureReason.DISK_SPACE_ERROR,
        detail="No space left on device",
        retryable=False,
    )
    expected = ArtifactDownloadError(failure)
    attempts = []

    def disk_full(*args, **kwargs):
        attempts.append(1)
        raise expected

    monkeypatch.setattr(ModrinthDownloader, "download_urls", disk_full)

    with pytest.raises(ArtifactDownloadError) as captured:
        ModrinthContentManager.ensure(instance)

    assert captured.value is expected
    assert attempts == [1]
