from pathlib import Path
from dataclasses import replace
import json
import zipfile

from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.models.instance.instance import Instance
from src.models.modrinth.project import ModrinthProject
from src.models.modrinth.version import ModrinthDependency, ModrinthFile, ModrinthVersion


def make_version(version_id: str, project_id: str, filename: str, dependencies=(), loader: str = "fabric") -> ModrinthVersion:
    return ModrinthVersion(version_id=version_id, project_id=project_id, name=version_id, version_number=version_id, version_type="release", game_versions=("1.20.1",), loaders=(loader,), files=(ModrinthFile(url=f"https://cdn.modrinth.com/{filename}", filename=filename, sha1="a", sha512="b", size=1, primary=True),), dependencies=tuple(dependencies), featured=True)


def write_fabric_mod(path: Path, mod_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": mod_id, "name": mod_id.title(), "version": "1.0.0", "environment": "client"}))




def write_forge_mod(path: Path, mod_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        'version="1.0.0"\n'
        f'displayName="{mod_id.title()}"\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)


def test_installs_required_dependencies_and_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Fabric", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))

    dependency = make_version("dep-version", "dep-project", "dependency.jar")
    root = make_version("root-version", "root-project", "root.jar", dependencies=(ModrinthDependency(dependency_type="required", project_id="dep-project"),))
    projects = {
        "root-project": ModrinthProject(project_id="root-project", slug="root", title="Root Mod", description="", project_type="mod", client_side="required"),
        "dep-project": ModrinthProject(project_id="dep-project", slug="dep", title="Dependency", description="", project_type="mod", client_side="required"),
    }

    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root)
    monkeypatch.setattr(ModrinthClient, "select_version", lambda project_id, game_version, loader="fabric", version_types=None: dependency)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: projects[project_id])

    def fake_download(file, destination, force=False, **kwargs):
        mod_id = "dependency" if file.filename.startswith("dependency") else "root"
        write_fabric_mod(destination, mod_id)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_file", fake_download)

    result = ModrinthModInstaller.install(instance, "root-version")

    assert result.installed_projects == ("Dependency", "Root Mod")
    assert (instance_dir / "mods" / "dependency.jar").is_file()
    assert (instance_dir / "mods" / "root.jar").is_file()
    registry = json.loads((instance_dir / ".mcw" / "modrinth.json").read_text(encoding="utf-8"))
    assert set(registry["mods"]) == {"dep-project", "root-project"}


def test_required_dependency_respects_enabled_release_channels(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Fabric", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))

    alpha_dependency = ModrinthVersion(version_id="dep-alpha", project_id="dep-project", name="Alpha", version_number="1.0-alpha", version_type="alpha", game_versions=("1.20.1",), loaders=("fabric",), files=(ModrinthFile(url="https://cdn.modrinth.com/dependency.jar", filename="dependency.jar", sha1="a", sha512="b", size=1, primary=True),), dependencies=(), featured=False)
    root = make_version("root-version", "root-project", "root.jar", dependencies=(ModrinthDependency(dependency_type="required", version_id="dep-alpha", project_id="dep-project"),))
    projects = {
        "root-project": ModrinthProject(project_id="root-project", slug="root", title="Root Mod", description="", project_type="mod", client_side="required"),
        "dep-project": ModrinthProject(project_id="dep-project", slug="dep", title="Dependency", description="", project_type="mod", client_side="required"),
    }

    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root if version_id == "root-version" else alpha_dependency)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: projects[project_id])

    import pytest
    with pytest.raises(RuntimeError, match="disabled alpha channel"):
        ModrinthModInstaller.install(instance, "root-version", allowed_version_types=("release",))


def test_installs_forge_mod_and_resolves_forge_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Forge", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.4.21"))

    dependency = make_version("dep-version", "dep-project", "dependency.jar", loader="forge")
    root = make_version("root-version", "root-project", "root.jar", dependencies=(ModrinthDependency(dependency_type="required", project_id="dep-project"),), loader="forge")
    projects = {
        "root-project": ModrinthProject(project_id="root-project", slug="root", title="Root Forge Mod", description="", project_type="mod", client_side="required"),
        "dep-project": ModrinthProject(project_id="dep-project", slug="dep", title="Forge Dependency", description="", project_type="mod", client_side="required"),
    }
    selected_loaders = []
    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root)
    monkeypatch.setattr(ModrinthClient, "select_version", lambda project_id, game_version, loader="fabric", version_types=None: selected_loaders.append(loader) or dependency)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: projects[project_id])

    def fake_download(file, destination, force=False, **kwargs):
        mod_id = "dependency" if file.filename.startswith("dependency") else "root"
        write_forge_mod(destination, mod_id)
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_file", fake_download)

    result = ModrinthModInstaller.install(instance, "root-version")

    assert result.installed_projects == ("Forge Dependency", "Root Forge Mod")
    assert selected_loaders == ["forge"]
    registry = json.loads((instance_dir / ".mcw" / "modrinth.json").read_text(encoding="utf-8"))
    assert registry["mods"]["root-project"]["loader"] == "forge"
    assert registry["mods"]["dep-project"]["loader"] == "forge"


def test_installs_forge_family_library_into_neoforge_when_modrinth_declares_both_loaders(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="NeoForge", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("neoforge", "47.1.106"))
    root = replace(make_version("kff-version", "kff-project", "kotlinforforge-4.12.0-all.jar", loader="forge"), version_number="4.12.0", loaders=("forge", "neoforge"))
    project = ModrinthProject(project_id="kff-project", slug="kotlin-for-forge", title="Kotlin for Forge", description="", project_type="mod", client_side="required")
    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: project)

    def fake_download(file, destination, force=False, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nFMLModType: LIBRARY\n")
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_file", fake_download)

    result = ModrinthModInstaller.install(instance, "kff-version")

    assert result.installed_projects == ("Kotlin for Forge",)
    installed = ModManager.list_mods(instance)
    assert len(installed) == 1
    assert installed[0].loader == "neoforge"
    assert installed[0].status == "Ready"


def test_rejects_modrinth_version_for_wrong_instance_loader(tmp_path, monkeypatch):
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance = Instance(instance_id="id", name="Forge", version_id="1.20.1", instance_dir=tmp_path, mod_loader=("forge", "47.4.21"))
    root = make_version("root-version", "root-project", "root.jar", loader="fabric")
    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root)

    import pytest
    with pytest.raises(RuntimeError, match="does not support Forge"):
        ModrinthModInstaller.install(instance, "root-version")


def test_accepts_advisory_nearby_patch_metadata_for_jar_validation():
    version = replace(
        make_version("root-version", "root-project", "root.jar"),
        game_versions=("1.20.4",),
    )

    ModrinthModInstaller._validate_version(version, "1.20.1", "fabric")


def test_installs_fabric_tagged_mod_into_quilt_instance(tmp_path, monkeypatch):
    instance_dir = tmp_path / "quilt-instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="quilt-id", name="Quilt", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("quilt", "0.27.1"))
    root = make_version("fabric-compatible", "project", "fabric-compatible.jar", loader="fabric")

    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: root)
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: ModrinthProject(project_id=project_id, slug="compatible", title="Compatible", description="", project_type="mod", client_side="required"))

    def fake_download(file, destination, **kwargs):
        write_fabric_mod(destination, "compatible_mod")
        return destination

    monkeypatch.setattr(ModrinthDownloader, "download_file", fake_download)

    result = ModrinthModInstaller.install(instance, root)

    installed = ModManager.list_mods(instance)
    assert result.installed_files == ("fabric-compatible.jar",)
    assert installed[0].loader == "quilt"
    assert installed[0].metadata_format == "fabric.mod.json (Quilt compatibility)"
