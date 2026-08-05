from pathlib import Path

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.core.modrinth.modrinth_mod_update_manager import ModrinthModUpdateManager
from src.core.progress.progress_reporter import ProgressReporter
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.models.instance.instance import Instance
from src.models.modrinth.install_result import ModrinthModInstallResult
from src.models.modrinth.version import ModrinthFile, ModrinthVersion


def make_instance(tmp_path: Path, loader: str = "fabric") -> Instance:
    instance_dir = tmp_path / "instance"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="id", name="Test", version_id="1.20.1", instance_dir=instance_dir, mod_loader=(loader, "47.4.21" if loader == "forge" else "0.16.0"))
    (instance_dir / "mods" / "example.jar").write_bytes(b"jar")
    ModrinthRegistry.save(instance, {"mods": {"project": {"projectId": "project", "versionId": "old", "versionNumber": "1.0", "versionType": "release", "fileName": "example.jar", "title": "Example", "locked": False}}})
    return instance


def version(version_id: str, number: str, loader: str = "fabric") -> ModrinthVersion:
    return ModrinthVersion(version_id=version_id, project_id="project", name=number, version_number=number, version_type="release", game_versions=("1.20.1",), loaders=(loader,), files=(ModrinthFile(url="https://cdn.modrinth.com/example.jar", filename="example.jar", sha1="a", sha512="b", size=1, primary=True),), date_published="2026-01-01T00:00:00Z")


def test_reports_compatible_update(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda *args, **kwargs: [version("new", "2.0")])

    report = ModrinthModUpdateManager.check(instance, ("release",))

    assert report.update_count == 1
    assert report.entries[0].latest_version_number == "2.0"


def test_skips_locked_mod_during_update_all(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    ModrinthRegistry.set_locked(instance, ["project"], True)
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda current: False)
    monkeypatch.setattr(ModrinthClient, "select_version", lambda *args, **kwargs: version("new", "2.0"))
    monkeypatch.setattr(ModrinthModInstaller, "install", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("locked mod must not install")))

    result = ModrinthModUpdateManager.update_all(instance, ("release",))

    assert result.skipped_locked == ("Example",)
    assert result.updated_projects == ()


def test_updates_unlocked_mod(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda current: False)
    monkeypatch.setattr(ModrinthClient, "select_version", lambda *args, **kwargs: version("new", "2.0"))
    monkeypatch.setattr(ModrinthModInstaller, "install", lambda *args, **kwargs: ModrinthModInstallResult(installed_projects=("Example",), installed_files=("example-2.jar",)))

    result = ModrinthModUpdateManager.update(instance, ["project"], ("release",))

    assert result.updated_projects == ("Example",)
    assert result.updated_files == ("example-2.jar",)


def test_forge_update_check_uses_forge_loader_filter(tmp_path, monkeypatch):
    instance = make_instance(tmp_path, loader="forge")
    seen = []
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda project_id, loader, **kwargs: seen.append(loader) or [version("new", "2.0", loader="forge")])

    report = ModrinthModUpdateManager.check(instance, ("release",))

    assert report.update_count == 1
    assert seen == ["forge"]


def test_update_check_reports_tracked_mod_progress(tmp_path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    monkeypatch.setattr(ModrinthClient, "list_project_versions", lambda *args, **kwargs: [version("new", "2.0")])
    events = []

    ModrinthModUpdateManager.check(instance, ("release",), reporter=ProgressReporter(events.append))

    assert [event.current for event in events] == [0, 1]
    assert [event.total for event in events] == [1, 1]
    assert events[-1].message == "mods.update_check.checked_project"
