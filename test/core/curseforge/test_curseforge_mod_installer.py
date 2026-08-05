from __future__ import annotations

from pathlib import Path
import json
import zipfile

import pytest

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader
from src.core.curseforge.curseforge_mod_installer import CurseForgeModInstaller
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.progress.progress_reporter import ProgressReporter
from src.models.curseforge.file import CurseForgeDependency, CurseForgeFile
from src.models.curseforge.project import CurseForgeProject
from src.models.instance.instance import Instance
from src.models.progress.progress_unit import ProgressUnit


def make_file(*, project_id: int = 10, file_id: int = 20, file_name: str = "root.jar", loaders: tuple[str, ...] = ("fabric",), dependencies: tuple[CurseForgeDependency, ...] = ()) -> CurseForgeFile:
    return CurseForgeFile(
        file_id=file_id,
        project_id=project_id,
        display_name=f"Project {project_id} build",
        file_name=file_name,
        release_type="release",
        file_date="2026-07-25T00:00:00Z",
        file_length=100,
        download_url=f"https://example.invalid/{file_name}",
        sha1="a" * 40,
        game_versions=("1.20.1",),
        dependencies=dependencies,
        loaders=loaders,
    )


def make_project(project_id: int, name: str) -> CurseForgeProject:
    return CurseForgeProject(
        project_id=project_id,
        name=name,
        slug=name.casefold().replace(" ", "-"),
        summary="Test project",
        download_count=100,
        authors=("Tester",),
        logo_url="",
        class_id=6,
        date_modified="2026-07-25T00:00:00Z",
        project_url=f"https://www.curseforge.com/minecraft/mc-mods/{project_id}",
        game_versions=("1.20.1",),
        loaders=("fabric",),
    )


def make_instance(tmp_path: Path) -> Instance:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    return Instance(
        instance_id="fabric-instance",
        name="Fabric Test",
        version_id="1.20.1",
        instance_dir=instance_dir,
        mod_loader=("fabric", "0.16.14"),
    )


def write_fabric_mod(path: Path, mod_id: str, name: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": name or mod_id,
        "version": "1.0.0",
        "environment": "client",
        "depends": {"fabricloader": ">=0.16.0", "minecraft": "1.20.1"},
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(metadata))
    return path


def write_forge_mod(path: Path, mod_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        'version="1.0.0"\n'
        f'displayName="{mod_id}"\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)
    return path


@pytest.fixture(autouse=True)
def isolated_paths_and_unlocked_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: False))


def configure_catalog(monkeypatch: pytest.MonkeyPatch, root: CurseForgeFile, dependencies: dict[int, CurseForgeFile] | None = None) -> dict[int, CurseForgeProject]:
    dependency_files = dependencies or {}
    files = {root.project_id: root, **dependency_files}
    projects = {
        project_id: make_project(project_id, "Root Mod" if project_id == root.project_id else f"Dependency {project_id}")
        for project_id in files
    }
    monkeypatch.setattr(CurseForgeClient, "get_file", staticmethod(lambda project_id, file_id: root))
    monkeypatch.setattr(
        CurseForgeClient,
        "latest_compatible_file",
        staticmethod(lambda project_id, *_args, **_kwargs: dependency_files[int(project_id)]),
    )
    monkeypatch.setattr(
        CurseForgeClient,
        "get_projects_batch",
        staticmethod(lambda project_ids: {int(project_id): projects[int(project_id)] for project_id in project_ids}),
    )
    monkeypatch.setattr(CurseForgeClient, "get_project", staticmethod(lambda project_id: projects[int(project_id)]))
    return projects


def test_build_plan_accepts_advisory_loader_mismatch_for_jar_validation() -> None:
    root = make_file(loaders=("fabric",))

    plan = CurseForgeModInstaller._build_plan(
        root,
        game_version="1.20.1",
        loader="forge",
        install_dependencies=False,
        allowed_release_types=("release",),
    )

    assert plan == [root]


def test_build_plan_allows_missing_game_version_metadata_for_jar_validation() -> None:
    original = make_file(loaders=("fabric",))
    root = CurseForgeFile(
        file_id=original.file_id,
        project_id=original.project_id,
        display_name=original.display_name,
        file_name=original.file_name,
        release_type=original.release_type,
        file_date=original.file_date,
        file_length=original.file_length,
        download_url=original.download_url,
        sha1=original.sha1,
        game_versions=(),
        dependencies=original.dependencies,
        loaders=original.loaders,
    )

    plan = CurseForgeModInstaller._build_plan(
        root,
        game_version="1.20.1",
        loader="forge",
        install_dependencies=False,
        allowed_release_types=("release",),
    )

    assert plan == [root]


def test_build_plan_allows_advisory_nearby_patch_metadata_for_jar_validation() -> None:
    original = make_file(loaders=("fabric",))
    root = CurseForgeFile(
        file_id=original.file_id,
        project_id=original.project_id,
        display_name=original.display_name,
        file_name=original.file_name,
        release_type=original.release_type,
        file_date=original.file_date,
        file_length=original.file_length,
        download_url=original.download_url,
        sha1=original.sha1,
        game_versions=("1.20.4",),
        dependencies=original.dependencies,
        loaders=original.loaders,
    )

    plan = CurseForgeModInstaller._build_plan(
        root,
        game_version="1.20.1",
        loader="fabric",
        install_dependencies=False,
        allowed_release_types=("release",),
    )

    assert plan == [root]


def test_installs_fabric_mod_and_required_dependency_with_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dependency = make_file(project_id=11, file_id=21, file_name="fabric-api.jar")
    root = make_file(dependencies=(CurseForgeDependency(project_id=11, relation_type=3),))
    projects = configure_catalog(monkeypatch, root, {11: dependency})
    events = []

    def download(file: CurseForgeFile, destination: Path, reporter=None, stage=None, message=None, **_kwargs) -> Path:
        mod_id = "fabric_api" if file.project_id == 11 else "root_mod"
        write_fabric_mod(destination, mod_id)
        if reporter is not None:
            reporter.bytes(stage, message or file.file_name, current=100, total=100)
        return destination

    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(download))
    instance = make_instance(tmp_path)

    result = CurseForgeModInstaller.install(
        instance,
        root.project_id,
        root.file_id,
        reporter=ProgressReporter(events.append),
    )

    assert result.installed_projects == (projects[11].name, projects[10].name)
    assert result.installed_files == ("fabric-api.jar", "root.jar")
    assert {path.name for path in (instance.instance_dir / "mods").glob("*.jar")} == {"fabric-api.jar", "root.jar"}
    registry = CurseForgeRegistry.load(instance)
    assert registry["mods"]["10"]["loader"] == "fabric"
    assert registry["mods"]["10"]["validatedLoader"] == "fabric"
    assert registry["mods"]["11"]["modId"] == "fabric_api"
    assert any(event.unit == ProgressUnit.BYTES for event in events)
    assert events[-1].current == events[-1].total == 2


def test_wrong_loader_dependency_is_rejected_before_instance_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dependency = make_file(project_id=11, file_id=21, file_name="wrong-dependency.jar", loaders=("forge",))
    root = make_file(dependencies=(CurseForgeDependency(project_id=11, relation_type=3),))
    configure_catalog(monkeypatch, root, {11: dependency})

    def download(file: CurseForgeFile, destination: Path, **_kwargs) -> Path:
        if file.project_id == 11:
            return write_forge_mod(destination, "wrong_dependency")
        return write_fabric_mod(destination, "root_mod")

    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(download))
    instance = make_instance(tmp_path)
    mods_dir = Paths.instance_mods_dir(instance)
    sentinel = mods_dir / "keep.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Forge mod"):
        CurseForgeModInstaller.install(
            instance,
            root.project_id,
            root.file_id,
            allow_unverified=True,
        )

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(mods_dir.glob("*.jar")) == []
    assert not Paths.curseforge_instance_registry(instance).exists()


def test_registry_failure_rolls_back_replaced_mod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = make_file()
    configure_catalog(monkeypatch, root)
    monkeypatch.setattr(
        CurseForgeDownloader,
        "download_file",
        staticmethod(lambda file, destination, **_kwargs: write_fabric_mod(destination, "root_mod", "New Root")),
    )
    instance = make_instance(tmp_path)
    mods_dir = Paths.instance_mods_dir(instance)
    old_mod = write_fabric_mod(mods_dir / "old-root.jar", "root_mod", "Old Root")
    original_registry = CurseForgeRegistry.empty()
    original_registry["mods"]["10"] = {
        "projectId": 10,
        "fileId": 19,
        "fileName": old_mod.name,
        "displayName": "Old Root",
        "sha1": "b" * 40,
        "size": old_mod.stat().st_size,
    }
    CurseForgeRegistry.save(instance, original_registry)
    registry_path = Paths.curseforge_instance_registry(instance)
    registry_before = registry_path.read_bytes()
    monkeypatch.setattr(
        CurseForgeRegistry,
        "save",
        staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full"))),
    )

    with pytest.raises(OSError, match="disk full"):
        CurseForgeModInstaller.install(instance, root.project_id, root.file_id)

    assert old_mod.is_file()
    assert not (mods_dir / "root.jar").exists()
    assert registry_path.read_bytes() == registry_before
    transaction_root = Paths.curseforge_instance_transaction_root(instance)
    assert list(transaction_root.iterdir()) == []
