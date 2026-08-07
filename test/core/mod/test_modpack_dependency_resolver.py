from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
import zipfile

import pytest

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.core.mod.mod_manager import ModManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.mod.modpack_dependency_resolver import ModpackDependencyResolver
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.models.curseforge.file import CurseForgeDependency, CurseForgeFile
from src.models.mod.dependency_resolution import DependencyResolutionResult, RequiredModDependenciesMissing
from src.models.mod.mod_info import ModInfo
from src.models.mod.mod_issue import ModHealthReport, ModIssue
from src.models.modrinth.project import ModrinthProject
from src.models.modrinth.version import ModrinthDependency, ModrinthFile, ModrinthVersion


def instance(tmp_path, loader="neoforge"):
    return SimpleNamespace(name="Pack", version_id="1.21.1", mod_loader=(loader, "21.1.200"), instance_dir=tmp_path / "Pack")


def mr_version(version_id: str, project_id: str, filename: str, dependencies=()):
    return ModrinthVersion(
        version_id=version_id,
        project_id=project_id,
        name=version_id,
        version_number=version_id,
        version_type="release",
        game_versions=("1.21.1",),
        loaders=("neoforge",),
        files=(ModrinthFile(url=f"https://cdn.modrinth.com/data/{project_id}/versions/{version_id}/{filename}", filename=filename, sha1=(project_id[0] * 40), sha512=(project_id[0] * 128), size=10, primary=True),),
        dependencies=tuple(dependencies),
    )


def cf_file(project_id: int, file_id: int, filename: str, dependencies=()):
    return CurseForgeFile(
        file_id=file_id,
        project_id=project_id,
        display_name=filename,
        file_name=filename,
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url=f"https://edge.forgecdn.net/files/{file_id}/{filename}",
        sha1=(str(project_id)[0] * 40),
        game_versions=("1.21.1",),
        dependencies=tuple(dependencies),
        loaders=("neoforge",),
    )


def test_modrinth_resolver_adds_recursive_required_dependencies(tmp_path, monkeypatch):
    root = mr_version("root-v", "root", "root.jar", (ModrinthDependency("required", project_id="dep-a"),))
    dep_a = mr_version("a-v", "dep-a", "a.jar", (ModrinthDependency("required", project_id="dep-b"),))
    dep_b = mr_version("b-v", "dep-b", "b.jar")
    versions = {item.version_id: item for item in (root, dep_a, dep_b)}
    projects = {project_id: ModrinthProject(project_id=project_id, slug=project_id, title=project_id.title(), description="", project_type="mod") for project_id in ("root", "dep-a", "dep-b")}
    registry = {"projectId": "pack", "versionId": "pack-v", "managedFiles": [{"path": "mods/root.jar", "fileName": "root.jar", "source": "download", "provider": "modrinth", "projectId": "root", "versionId": "root-v", "sha1": "r" * 40, "sha512": "r" * 128, "size": 10, "downloads": ["https://cdn.modrinth.com/root.jar"]}]}
    saved = {}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(ModrinthPackRegistry, "save", lambda _dir, payload: saved.update(payload))
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: versions[version_id])
    monkeypatch.setattr(ModrinthClient, "select_version", lambda project_id, **_kwargs: {"dep-a": dep_a, "dep-b": dep_b}[project_id])
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: projects[project_id])

    result = ModpackDependencyResolver.resolve(instance(tmp_path))

    assert result.added_files == ("Dep-A", "Dep-B")
    by_project = {entry.get("projectId"): entry for entry in saved["managedFiles"]}
    assert by_project["dep-a"]["selectionReason"] == "required_dependency"
    assert by_project["dep-a"]["requiredBy"] == ["root.jar"]
    assert by_project["dep-b"]["requiredBy"] == ["Dep-A"]


def test_modrinth_resolver_keeps_pack_pinned_dependency_version(tmp_path, monkeypatch):
    root = mr_version("root-v", "root", "root.jar", (ModrinthDependency("required", project_id="dep", version_id="new-v"),))
    old = mr_version("old-v", "dep", "dep-old.jar")
    registry = {"managedFiles": [
        {"path": "mods/root.jar", "fileName": "root.jar", "source": "download", "provider": "modrinth", "projectId": "root", "versionId": "root-v", "sha1": "r" * 40, "sha512": "r" * 128, "size": 10, "downloads": []},
        {"path": "mods/dep-old.jar", "fileName": "dep-old.jar", "source": "download", "provider": "modrinth", "projectId": "dep", "versionId": "old-v", "sha1": "d" * 40, "sha512": "d" * 128, "size": 10, "downloads": []},
    ]}
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(ModrinthPackRegistry, "save", lambda *_args: None)
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(ModrinthClient, "get_version", lambda version_id: {"root-v": root, "old-v": old}[version_id])

    result = ModpackDependencyResolver.resolve(instance(tmp_path))

    assert not result.added_files
    assert any("pack-pinned file was kept" in warning for warning in result.warnings)
    assert registry["managedFiles"][1]["requiredBy"] == ["root.jar"]


def test_curseforge_resolver_adds_only_required_dependencies(tmp_path, monkeypatch):
    root = cf_file(10, 100, "root.jar", (CurseForgeDependency(20, 3), CurseForgeDependency(30, 2)))
    required = cf_file(20, 200, "required.jar")
    registry = {"managedFiles": [{"projectId": 10, "fileId": 100, "fileName": "root.jar", "path": "mods/root.jar", "provider": "curseforge", "required": True}]}
    saved = {}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _file_ids: {100: root})
    monkeypatch.setattr(CurseForgeClient, "get_file", lambda project_id, file_id: root if project_id == 10 else required)
    monkeypatch.setattr(CurseForgeClient, "latest_compatible_file", lambda project_id, *_args, **_kwargs: required if project_id == 20 else pytest.fail("optional dependency must not be resolved"))
    monkeypatch.setattr(CurseForgeClient, "get_project", lambda project_id: SimpleNamespace(name="Required", project_url="https://www.curseforge.com/minecraft/mc-mods/required"))

    result = ModpackDependencyResolver.resolve(instance(tmp_path))

    assert result.added_files == ("Required",)
    added = next(entry for entry in saved["managedFiles"] if entry["projectId"] == 20)
    assert added["selectionReason"] == "required_dependency"
    assert added["requiredBy"] == ["root.jar"]


def test_pack_pinned_system_requirement_mismatch_is_warning(tmp_path):
    mod = ModInfo(
        path=tmp_path / "jei.jar",
        file_name="jei.jar",
        enabled=True,
        mod_id="jei",
        name="Just Enough Items",
        version="19.0.0",
        loader="neoforge",
        dependencies={"minecraft": "[1.21, 1.21.1)"},
        managed_by_modpack=True,
    )

    report = ModCompatibilityManager.scan(instance(tmp_path), mods=[mod])

    assert report.error_count == 0
    assert report.warning_count == 1
    assert report.issues[0].code == "pack-pinned-system-requirement"


def test_required_dependency_errors_cannot_be_bypassed_for_managed_pack(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path)
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {"managedFiles": [{"path": "mods/root.jar"}]})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: {})
    issue = ModIssue("error", "dependency-missing", "FancyMenu requires missing dependency 'konkrete'.", ("fancymenu", "konkrete"))
    monkeypatch.setattr(ModCompatibilityManager, "scan", lambda _instance: ModHealthReport((issue,), 1, 0))

    with pytest.raises(RequiredModDependenciesMissing, match="konkrete"):
        ModpackDependencyResolver.raise_for_required_dependencies(managed_instance)


def test_curseforge_mod_uses_exact_modrinth_mirror_to_recover_kotlinforforge(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.19.2"
    managed_instance.instance_dir.mkdir(parents=True)
    parent = ModInfo(
        path=managed_instance.instance_dir / "mods" / "slice-and-dice.jar",
        file_name="slice-and-dice.jar",
        enabled=True,
        mod_id="sliceanddice",
        name="Create Slice & Dice",
        version="2.4.0",
        loader="forge",
        dependencies={"create": "*", "kotlinforforge": "[3.9.1,)"},
        source="curseforge",
        managed_by_modpack=True,
        source_pack_provider="curseforge",
    )
    create = ModInfo(
        path=managed_instance.instance_dir / "mods" / "create.jar",
        file_name="create.jar",
        enabled=True,
        mod_id="create",
        name="Create",
        version="0.5.1",
        loader="forge",
        managed_by_modpack=True,
        source="curseforge",
        source_pack_provider="curseforge",
    )
    mirror = ModrinthVersion(
        version_id="slice-mirror",
        project_id="slice-project",
        name="Create Slice & Dice 2.4.0",
        version_number="2.4.0",
        version_type="release",
        game_versions=("1.19.2",),
        loaders=("forge",),
        files=(ModrinthFile("https://cdn.modrinth.com/slice.jar", "slice-and-dice.jar", "a" * 40, "a" * 128, 10, True),),
        dependencies=(
            ModrinthDependency("required", project_id="create-project"),
            ModrinthDependency("required", project_id="kff-project"),
        ),
    )
    create_version = ModrinthVersion(
        version_id="create-version",
        project_id="create-project",
        name="Create",
        version_number="0.5.1",
        version_type="release",
        game_versions=("1.19.2",),
        loaders=("forge",),
        files=(ModrinthFile("https://cdn.modrinth.com/create.jar", "create.jar", "b" * 40, "b" * 128, 10, True),),
    )
    kff_version = ModrinthVersion(
        version_id="kff-version",
        project_id="kff-project",
        name="Kotlin for Forge 3.9.1",
        version_number="3.9.1",
        version_type="release",
        game_versions=("1.19.2",),
        loaders=("forge",),
        files=(ModrinthFile("https://cdn.modrinth.com/kff.jar", "kotlinforforge-3.9.1-all.jar", "c" * 40, "c" * 128, 10, True),),
    )
    projects = {
        "create-project": ModrinthProject("create-project", "create", "Create", "", "mod"),
        "kff-project": ModrinthProject("kff-project", "kotlin-for-forge", "Kotlin for Forge", "", "mod"),
    }
    direct_registry = {"mods": {}}
    saved = {}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: {"managedFiles": [{"path": "mods/slice-and-dice.jar"}]})
    monkeypatch.setattr(ModpackDependencyResolver, "_resolve_curseforge", staticmethod(lambda *_args, **_kwargs: DependencyResolutionResult()))
    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [parent, create])
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {"slice-and-dice.jar": {"sha1": "a" * 40}})
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(ModrinthRegistry, "load", lambda _instance: direct_registry)
    monkeypatch.setattr(ModrinthRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(ModrinthClient, "get_version_from_hash", lambda value, algorithm="sha512": mirror if value == "a" * 40 and algorithm == "sha1" else None)
    monkeypatch.setattr(ModrinthClient, "select_version", lambda project_id, **_kwargs: {"create-project": create_version, "kff-project": kff_version}[project_id])
    monkeypatch.setattr(ModrinthClient, "get_project", lambda project_id: projects[project_id])

    result = ModpackDependencyResolver.resolve(managed_instance)

    assert result.added_files == ("Kotlin for Forge",)
    assert set(saved["mods"]) == {"kff-project"}
    entry = saved["mods"]["kff-project"]
    assert entry["versionId"] == "kff-version"
    assert entry["expectedModId"] == "kotlinforforge"
    assert entry["managedByModpack"] is True
    assert entry["selectionReason"] == "required_dependency"
    assert entry["requiredBy"] == ["Create Slice & Dice"]
    assert entry["packProvider"] == "curseforge"
    assert entry["locked"] is True


def test_prunes_auto_added_standalone_dependency_when_another_mod_embeds_it(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.instance_dir.mkdir(parents=True)
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir()
    create_path = mods_dir / "create.jar"
    flywheel_path = mods_dir / "flywheel-forge-1.19.2-0.6.8.a.jar"
    create_path.write_bytes(b"create")
    flywheel_path.write_bytes(b"old-flywheel")
    create = ModInfo(
        path=create_path,
        file_name=create_path.name,
        enabled=True,
        mod_id="create",
        name="Create",
        version="0.5.1.f",
        loader="forge",
        provided_mods=(("flywheel", "0.6.10-20"),),
        managed_by_modpack=True,
        source="curseforge",
        source_pack_provider="curseforge",
    )
    flywheel = ModInfo(
        path=flywheel_path,
        file_name=flywheel_path.name,
        enabled=True,
        mod_id="flywheel",
        name="Flywheel",
        version="0.6.8.a",
        loader="forge",
        managed_by_modpack=True,
        source="curseforge",
        source_pack_provider="curseforge",
    )
    curseforge_pack = {
        "managedFiles": [
            {"path": f"mods/{create.file_name}", "fileName": create.file_name, "selectionReason": "pack_manifest"},
            {"path": f"mods/{flywheel.file_name}", "fileName": flywheel.file_name, "selectionReason": "required_dependency"},
        ]
    }
    saved = {}
    removed = []

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [create, flywheel])
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {
        create.file_name.casefold(): {"selectionReason": "pack_manifest"},
        flywheel.file_name.casefold(): {"selectionReason": "required_dependency"},
    })
    monkeypatch.setattr(ModProvenanceRegistry, "remove_by_filenames", lambda _instance, names: removed.extend(names) or tuple(names))
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(ModrinthPackRegistry, "save", lambda *_args: None)
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: curseforge_pack)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(ModrinthRegistry, "load", lambda _instance: {"mods": {}})
    monkeypatch.setattr(ModrinthRegistry, "save", lambda *_args: None)

    messages = ModpackDependencyResolver._prune_redundant_embedded_dependencies(managed_instance)

    assert not flywheel_path.exists()
    assert create_path.exists()
    assert removed == [flywheel.file_name]
    assert [entry["fileName"] for entry in saved["managedFiles"]] == [create.file_name]
    assert any("already provides mod ID 'flywheel'" in message for message in messages)


def test_prunes_superseded_required_dependency_when_pack_manifest_pins_same_project(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.instance_dir.mkdir(parents=True)
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir()
    current_path = mods_dir / "cc-tweaked-1.116.1.jar"
    stale_path = mods_dir / "cc-tweaked-1.113.1.jar"
    current_path.write_bytes(b"current")
    stale_path.write_bytes(b"stale")
    current = ModInfo(path=current_path, file_name=current_path.name, enabled=True, mod_id="computercraft", name="CC:Tweaked", version="1.116.1", loader="forge", managed_by_modpack=True, source="curseforge", source_project_id="236307", source_pack_provider="curseforge")
    stale = ModInfo(path=stale_path, file_name=stale_path.name, enabled=True, mod_id="computercraft", name="CC:Tweaked", version="1.113.1", loader="forge", managed_by_modpack=True, source="curseforge", source_project_id="236307", source_pack_provider="curseforge")
    pack = {
        "managedFiles": [
            {"projectId": 236307, "fileId": 2, "path": f"mods/{current.file_name}", "fileName": current.file_name, "selectionReason": "pack_manifest"},
            {"projectId": 236307, "fileId": 1, "path": f"mods/{stale.file_name}", "fileName": stale.file_name, "selectionReason": "required_dependency"},
        ]
    }
    saved = {}

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [current, stale])
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {
        current.file_name.casefold(): {"selectionReason": "pack_manifest", "provider": "curseforge", "projectId": "236307"},
        stale.file_name.casefold(): {"selectionReason": "required_dependency", "provider": "curseforge", "projectId": "236307"},
    })
    monkeypatch.setattr(ModProvenanceRegistry, "remove_by_filenames", lambda *_args: ())
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(ModrinthPackRegistry, "save", lambda *_args: None)
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: pack)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(ModrinthRegistry, "load", lambda _instance: {"mods": {}})
    monkeypatch.setattr(ModrinthRegistry, "save", lambda *_args: None)

    messages = ModpackDependencyResolver._prune_redundant_embedded_dependencies(managed_instance)

    assert current_path.exists()
    assert not stale_path.exists()
    assert [entry["fileName"] for entry in saved["managedFiles"]] == [current.file_name]
    assert any("pack manifest already pins" in message for message in messages)


def test_does_not_prune_modified_managed_dependency_when_recorded_hash_differs(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.instance_dir.mkdir(parents=True)
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir()
    current_path = mods_dir / "current.jar"
    stale_path = mods_dir / "stale-but-modified.jar"
    current_path.write_bytes(b"current")
    stale_path.write_bytes(b"user-modified")
    current = ModInfo(path=current_path, file_name=current_path.name, enabled=True, mod_id="example", name="Current", version="2.0", loader="forge", managed_by_modpack=True, source="curseforge", source_project_id="10", source_pack_provider="curseforge")
    stale = ModInfo(path=stale_path, file_name=stale_path.name, enabled=True, mod_id="example", name="Stale", version="1.0", loader="forge", managed_by_modpack=True, source="curseforge", source_project_id="10", source_pack_provider="curseforge")

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [current, stale])
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {
        current.file_name.casefold(): {"selectionReason": "pack_manifest", "provider": "curseforge", "projectId": "10"},
        stale.file_name.casefold(): {"selectionReason": "required_dependency", "provider": "curseforge", "projectId": "10", "sha1": "0" * 40},
    })

    messages = ModpackDependencyResolver._prune_redundant_embedded_dependencies(managed_instance)

    assert messages == ()
    assert current_path.exists()
    assert stale_path.read_bytes() == b"user-modified"


def test_does_not_prune_user_added_duplicate_without_required_dependency_provenance(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.instance_dir.mkdir(parents=True)
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir()
    pack_path = mods_dir / "pack-copy.jar"
    user_path = mods_dir / "user-copy.jar"
    pack_path.write_bytes(b"pack")
    user_path.write_bytes(b"user")
    pack_mod = ModInfo(path=pack_path, file_name=pack_path.name, enabled=True, mod_id="example", name="Pack Copy", version="2.0", loader="forge", managed_by_modpack=True, source="curseforge", source_project_id="10", source_pack_provider="curseforge")
    user_mod = ModInfo(path=user_path, file_name=user_path.name, enabled=True, mod_id="example", name="User Copy", version="1.0", loader="forge", managed_by_modpack=False, source="local")

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [pack_mod, user_mod])
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {
        pack_mod.file_name.casefold(): {"selectionReason": "pack_manifest", "provider": "curseforge", "projectId": "10"},
        user_mod.file_name.casefold(): {"selectionReason": "direct_install", "provider": "local"},
    })

    messages = ModpackDependencyResolver._prune_redundant_embedded_dependencies(managed_instance)

    assert messages == ()
    assert pack_path.exists()
    assert user_path.exists()


def test_curseforge_resolver_does_not_add_standalone_dependency_already_provided_by_embedded_mod(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    root = cf_file(10, 100, "addon.jar", (CurseForgeDependency(20, 3),))
    flywheel = cf_file(20, 200, "flywheel.jar")
    registry = {"managedFiles": [{"projectId": 10, "fileId": 100, "fileName": "addon.jar", "path": "mods/addon.jar", "provider": "curseforge", "required": True}]}
    create = ModInfo(
        path=tmp_path / "create.jar",
        file_name="create.jar",
        enabled=True,
        mod_id="create",
        name="Create",
        version="0.5.1.f",
        loader="forge",
        provided_mods=(("flywheel", "0.6.10-20"),),
    )

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [create])
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _ids: {100: root})
    monkeypatch.setattr(CurseForgeClient, "latest_compatible_file", lambda project_id, *_args, **_kwargs: flywheel if project_id == 20 else pytest.fail("unexpected project"))
    monkeypatch.setattr(CurseForgeClient, "get_project", lambda project_id: SimpleNamespace(name="Flywheel", slug="flywheel", project_url="https://example/flywheel"))
    saved = {}
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))

    result = ModpackDependencyResolver._resolve_curseforge(managed_instance, registry, None)

    assert result.added_files == ()
    assert len(registry["managedFiles"]) == 1
    assert len(saved["managedFiles"]) == 1


def test_curseforge_resolver_does_not_add_dependency_from_fallback_embedded_capability(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.20.1"
    managed_instance.mod_loader = ("forge", "47.4.0")
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir(parents=True)

    nested = BytesIO()
    with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "META-INF/mods.toml",
            'modLoader="javafml"\nloaderVersion="[47,)"\nlicense="MIT"\n\n[[mods]]\nmodId="expandability"\nversion="9.0.4"\ndisplayName="ExpandAbility"\n',
        )
    artifacts = mods_dir / "artifacts-forge-9.5.13.jar"
    with zipfile.ZipFile(artifacts, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "META-INF/mods.toml",
            'modLoader="javafml"\nloaderVersion="[47,)"\nlicense="MIT"\n\n[[mods]]\nmodId="artifacts"\nversion="9.5.13"\ndisplayName="Artifacts"\n',
        )
        archive.writestr("META-INF/jarjar/expandability-9.0.4.jar", nested.getvalue())

    root = CurseForgeFile(
        file_id=100,
        project_id=10,
        display_name="Artifacts",
        file_name=artifacts.name,
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=artifacts.stat().st_size,
        download_url="https://example/artifacts.jar",
        sha1="1" * 40,
        game_versions=("1.20.1",),
        dependencies=(CurseForgeDependency(20, 3),),
        loaders=("forge",),
    )
    dependency = CurseForgeFile(
        file_id=200,
        project_id=20,
        display_name="ExpandAbility",
        file_name="expandability-9.0.4.jar",
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url="https://example/expandability.jar",
        sha1="2" * 40,
        game_versions=("1.20.1",),
        dependencies=(),
        loaders=("forge",),
    )
    registry = {"managedFiles": [{"projectId": 10, "fileId": 100, "fileName": artifacts.name, "path": f"mods/{artifacts.name}", "provider": "curseforge", "required": True}]}

    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(ModProvenanceRegistry, "entries_by_file", lambda _instance: {})
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _file_ids: {100: root})
    monkeypatch.setattr(CurseForgeClient, "latest_compatible_file", lambda project_id, *_args, **_kwargs: dependency if project_id == 20 else pytest.fail("unexpected project"))
    monkeypatch.setattr(CurseForgeClient, "get_project", lambda _project_id: SimpleNamespace(name="ExpandAbility", slug="expandability", project_url="https://example/expandability"))
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda *_args: None)

    result = ModpackDependencyResolver._resolve_curseforge(managed_instance, registry, None)

    assert result.added_files == ()
    assert len(registry["managedFiles"]) == 1
    assert not (mods_dir / dependency.file_name).exists()


def test_repairs_pack_pinned_curseforge_dependency_missing_from_disk(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.12.2"
    managed_instance.instance_dir.mkdir(parents=True)
    compat = ModInfo(
        path=managed_instance.instance_dir / "mods" / "CompatSkills-1.12.2-1.17.0.jar",
        file_name="CompatSkills-1.12.2-1.17.0.jar",
        enabled=True,
        mod_id="compatskills",
        name="CompatSkills",
        version="1.17.0",
        loader="forge",
        dependencies={"reskillable": "*"},
        managed_by_modpack=True,
        source="curseforge",
        source_project_id="290541",
        source_file_id="2815687",
        source_pack_provider="curseforge",
    )
    registry = {
        "managedFiles": [
            {"projectId": 290541, "fileId": 2815687, "fileName": compat.file_name, "path": f"mods/{compat.file_name}", "selectionReason": "pack_manifest"},
            {"projectId": 286382, "fileId": 2815686, "fileName": "Reskillable-1.12.2-1.13.0.jar", "path": "mods/Reskillable-1.12.2-1.13.0.jar", "selectionReason": "pack_manifest", "pendingDownload": False},
        ]
    }
    projects = {
        290541: SimpleNamespace(project_id=290541, name="CompatSkills", slug="compatskills"),
        286382: SimpleNamespace(project_id=286382, name="Reskillable", slug="reskillable"),
    }
    saved = {}

    monkeypatch.setattr(ModManager, "list_mods", lambda _instance: [compat])
    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(CurseForgeClient, "get_projects_batch", lambda project_ids: {project_id: projects[project_id] for project_id in project_ids})

    result = ModpackDependencyResolver._reconcile_pack_pinned_dependencies(managed_instance, None)

    assert result.added_files == ("Reskillable",)
    entry = next(item for item in saved["managedFiles"] if item["projectId"] == 286382)
    assert entry["pendingDownload"] is True
    assert entry["retryableDownload"] is True
    assert entry["expectedModIds"] == ["reskillable"]
    assert entry["requiredBy"] == ["CompatSkills"]
    assert entry["projectSlug"] == "reskillable"


def test_pack_pinned_dependency_is_not_redownloaded_when_legacy_version_folder_is_scanned(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.12.2"
    mods_dir = managed_instance.instance_dir / "mods"
    version_dir = mods_dir / "1.12.2"
    version_dir.mkdir(parents=True)
    compat_path = mods_dir / "CompatSkills-1.12.2-1.17.0.jar"
    compat_metadata = [{"modid": "compatskills", "name": "CompatSkills", "version": "1.17.0", "requiredMods": ["required-after:reskillable"]}]
    reskillable_path = version_dir / "Reskillable-1.12.2-1.13.0.jar"
    reskillable_metadata = [{"modid": "reskillable", "name": "Reskillable", "version": "1.13.0", "mcversion": "1.12.2"}]
    import json
    import zipfile
    with zipfile.ZipFile(compat_path, "w") as archive:
        archive.writestr("mcmod.info", json.dumps(compat_metadata))
    with zipfile.ZipFile(reskillable_path, "w") as archive:
        archive.writestr("mcmod.info", json.dumps(reskillable_metadata))
    registry = {
        "managedFiles": [
            {"projectId": 290541, "fileId": 2815687, "fileName": compat_path.name, "path": f"mods/{compat_path.name}", "selectionReason": "pack_manifest"},
            {"projectId": 286382, "fileId": 2815686, "fileName": reskillable_path.name, "path": f"mods/1.12.2/{reskillable_path.name}", "selectionReason": "pack_manifest", "pendingDownload": False, "projectSlug": "reskillable", "expectedModIds": ["reskillable"]},
        ]
    }

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)

    result = ModpackDependencyResolver._reconcile_pack_pinned_dependencies(managed_instance, None)

    assert result.added_files == ()
    assert ModpackDependencyResolver.blocking_issues(managed_instance) == ()


def test_pack_pinned_verified_provider_file_is_not_marked_for_download_when_metadata_hides_mod_id(tmp_path, monkeypatch):
    from hashlib import sha1
    import json
    import zipfile

    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.12.2"
    mods_dir = managed_instance.instance_dir / "mods"
    mods_dir.mkdir(parents=True)
    compat_path = mods_dir / "CompatSkills-1.12.2-1.17.0.jar"
    reskillable_path = mods_dir / "Reskillable-1.12.2-1.13.0.jar"
    with zipfile.ZipFile(compat_path, "w") as archive:
        archive.writestr("mcmod.info", json.dumps([{
            "modid": "compatskills",
            "name": "CompatSkills",
            "version": "1.17.0",
            "requiredMods": ["required-after:reskillable"],
        }]))
    with zipfile.ZipFile(reskillable_path, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\nFMLModType: LIBRARY\nImplementation-Version: 1.13.0\n",
        )
        archive.writestr("codersafterdark/reskillable/Reskillable.class", b"legacy bytecode placeholder")

    registry = {
        "managedFiles": [
            {
                "projectId": 290541,
                "fileId": 2815687,
                "fileName": compat_path.name,
                "path": f"mods/{compat_path.name}",
                "selectionReason": "pack_manifest",
            },
            {
                "projectId": 286382,
                "fileId": 2815686,
                "fileName": reskillable_path.name,
                "path": f"mods/{reskillable_path.name}",
                "selectionReason": "pack_manifest",
                "pendingDownload": False,
                "projectName": "Reskillable",
                "projectSlug": "reskillable",
                "sha1": sha1(reskillable_path.read_bytes(), usedforsecurity=False).hexdigest(),
                "size": reskillable_path.stat().st_size,
            },
        ]
    }
    saved = {}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))

    result = ModpackDependencyResolver._reconcile_pack_pinned_dependencies(managed_instance, None)

    assert result.added_files == ()
    entry = next(item for item in saved["managedFiles"] if item["projectId"] == 286382)
    assert entry["pendingDownload"] is False
    assert entry["expectedModIds"] == ["reskillable"]
    assert entry["requiredBy"] == ["CompatSkills"]


def test_curseforge_resolver_ignores_dependency_metadata_from_foreign_loader(tmp_path, monkeypatch):
    root = CurseForgeFile(
        file_id=100,
        project_id=10,
        display_name="root.jar",
        file_name="root.jar",
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url="https://edge.forgecdn.net/files/100/root.jar",
        sha1="1" * 40,
        game_versions=("1.21.1",),
        dependencies=(CurseForgeDependency(20, 3),),
        loaders=("fabric",),
    )
    registry = {"managedFiles": [{"projectId": 10, "fileId": 100, "fileName": "root.jar", "path": "mods/root.jar", "provider": "curseforge", "required": True}]}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda *_args: None)
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _file_ids: {100: root})
    monkeypatch.setattr(CurseForgeClient, "latest_compatible_file", lambda *_args, **_kwargs: pytest.fail("foreign loader metadata must not expand the dependency graph"))

    result = ModpackDependencyResolver.resolve(instance(tmp_path, loader="neoforge"))

    assert result.added_files == ()
    assert result.unresolved == ()
    assert any("outside the active neoforge context" in warning for warning in result.warnings)


def test_curseforge_resolver_rejects_foreign_loader_dependency_candidate(tmp_path, monkeypatch):
    root = cf_file(10, 100, "root.jar", (CurseForgeDependency(20, 3),))
    foreign = CurseForgeFile(
        file_id=200,
        project_id=20,
        display_name="fabric-only.jar",
        file_name="fabric-only.jar",
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url="https://edge.forgecdn.net/files/200/fabric-only.jar",
        sha1="2" * 40,
        game_versions=("1.21.1",),
        dependencies=(CurseForgeDependency(30, 3),),
        loaders=("fabric",),
    )
    registry = {"managedFiles": [{"projectId": 10, "fileId": 100, "fileName": "root.jar", "path": "mods/root.jar", "provider": "curseforge", "required": True}]}
    saved = {}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda _instance, payload: saved.update(payload))
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _file_ids: {100: root})
    monkeypatch.setattr(CurseForgeClient, "latest_compatible_file", lambda project_id, *_args, **_kwargs: foreign if project_id == 20 else pytest.fail("foreign child metadata must not be traversed"))

    result = ModpackDependencyResolver.resolve(instance(tmp_path, loader="neoforge"))

    assert result.added_files == ()
    assert result.unresolved == ()
    assert not any("Ignored provider dependency from pack-pinned file" in warning for warning in result.warnings)
    assert all(entry.get("projectId") != 20 for entry in saved.get("managedFiles", registry["managedFiles"]))


def test_skyfactory5_pack_pinned_foreign_loader_metadata_does_not_create_dependency_blockers(tmp_path):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.20.1"
    managed_instance.mod_loader = ("forge", "47.4.0")
    mods = [
        ModInfo(path=tmp_path / "ForgeConfigAPIPort.jar", file_name="ForgeConfigAPIPort.jar", enabled=True, mod_id="forgeconfigapiport", name="Forge Config API Port", version="8.0.0", loader="fabric", dependencies={"fabric-api": ">=0.83.0", "fabricloader": ">=0.14.21"}, managed_by_modpack=True, source="curseforge", source_pack_provider="curseforge"),
        ModInfo(path=tmp_path / "minecraft_style_paintings.jar", file_name="minecraft_style_paintings.jar", enabled=True, mod_id="minecraft_style_paintings", name="minecraft style paintings", version="1.0.0", loader="neoforge", dependencies={"neoforge": "[21.1.65,)"}, managed_by_modpack=True, source="curseforge", source_pack_provider="curseforge"),
    ]

    report = ModCompatibilityManager.scan(managed_instance, mods=mods)

    assert not any(issue.severity == "error" for issue in report.issues)
    assert {issue.code for issue in report.issues} == {"pack-pinned-loader-metadata"}


def test_standalone_foreign_loader_mod_remains_strict_on_forge(tmp_path):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.20.1"
    managed_instance.mod_loader = ("forge", "47.4.0")
    mod = ModInfo(path=tmp_path / "fabric-only.jar", file_name="fabric-only.jar", enabled=True, mod_id="fabric_only", name="Fabric Only", version="1.0.0", loader="fabric", dependencies={"fabricloader": ">=0.14.21"}, managed_by_modpack=False)

    report = ModCompatibilityManager.scan(managed_instance, mods=[mod])

    assert any(issue.code == "loader-mismatch" and issue.severity == "error" for issue in report.issues)
    assert any(issue.code == "dependency-missing" and issue.severity == "error" for issue in report.issues)


def test_skyfactory5_pack_pinned_yacl_does_not_resolve_fabric_api_on_forge(tmp_path, monkeypatch):
    managed_instance = instance(tmp_path, loader="forge")
    managed_instance.version_id = "1.20.1"
    managed_instance.mod_loader = ("forge", "47.4.0")
    yacl = CurseForgeFile(
        file_id=9001,
        project_id=9000,
        display_name="YetAnotherConfigLib 3.4.2 for MC 1.20.1",
        file_name="yacl-forge.jar",
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url="https://example.invalid/yacl-forge.jar",
        sha1="9" * 40,
        game_versions=("1.20.1",),
        dependencies=(CurseForgeDependency(306612, 3),),
        loaders=("forge",),
    )
    fabric_api = CurseForgeFile(
        file_id=8443275,
        project_id=306612,
        display_name="Fabric API",
        file_name="fabric-api.jar",
        release_type="release",
        file_date="2026-01-01T00:00:00Z",
        file_length=10,
        download_url="https://example.invalid/fabric-api.jar",
        sha1="3" * 40,
        game_versions=("1.20.1",),
        dependencies=(),
        loaders=("fabric",),
    )
    registry = {"managedFiles": [{"projectId": 9000, "fileId": 9001, "fileName": "yacl-forge.jar", "path": "mods/yacl-forge.jar", "provider": "curseforge", "required": True, "selectionReason": "pack_manifest"}]}

    monkeypatch.setattr(ModrinthPackRegistry, "load", lambda _instance: {})
    monkeypatch.setattr(CurseForgePackRegistry, "load", lambda _instance: registry)
    monkeypatch.setattr(CurseForgePackRegistry, "save", lambda *_args: None)
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", lambda _instance: {})
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", lambda _file_ids: {9001: yacl})
    monkeypatch.setattr(CurseForgeClient, "list_files", lambda project_id, **_kwargs: [fabric_api] if int(project_id) == 306612 else [])

    result = ModpackDependencyResolver.resolve(managed_instance)

    assert result.added_files == ()
    assert result.unresolved == ()
    assert not any("CurseForge project 306612" in warning for warning in result.warnings)


def test_modpack_dependency_progress_is_batched_for_large_packs():
    from src.core.progress.progress_reporter import ProgressReporter

    events = []
    reporter = ProgressReporter(events.append)
    total = 178

    for current in range(total + 1):
        ModpackDependencyResolver._report(reporter, "Resolving CurseForge modpack dependencies...", current, total)

    assert events[0].current == 0
    assert events[-1].current == total
    assert len(events) <= 26
