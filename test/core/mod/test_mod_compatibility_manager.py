from pathlib import Path
import json
import zipfile

import pytest

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo


def make_instance(tmp_path: Path) -> Instance:
    instance_dir = tmp_path / "instance"
    (instance_dir / "mods").mkdir(parents=True)
    return Instance(instance_id="id", name="Test", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def write_mod(path: Path, mod_id: str, version: str = "1.0.0", depends=None, conflicts=None, breaks=None, enabled=True) -> Path:
    metadata = {"schemaVersion": 1, "id": mod_id, "name": mod_id, "version": version, "environment": "client", "depends": depends or {}}
    if conflicts:
        metadata["conflicts"] = conflicts
    if breaks:
        metadata["breaks"] = breaks
    target = path if enabled else path.with_name(path.name + ".disabled")
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(metadata))
    return target


def test_detects_duplicate_and_missing_fabric_api(tmp_path, monkeypatch):
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance = make_instance(tmp_path)
    mods = instance.instance_dir / "mods"
    write_mod(mods / "first.jar", "example", depends={"fabric-api": ">=0.90.0"})
    write_mod(mods / "second.jar", "example")

    report = ModCompatibilityManager.scan(instance)

    codes = {issue.code for issue in report.issues}
    assert "duplicate-mod-id" in codes
    assert "dependency-missing" in codes
    assert report.error_count == 2


def test_provided_capabilities_do_not_count_as_duplicate_primary_mod_ids(tmp_path) -> None:
    instance = make_instance(tmp_path)
    first = ModInfo(
        path=tmp_path / "create.jar",
        file_name="create.jar",
        enabled=True,
        mod_id="create",
        name="Create",
        version="1.0.0",
        loader="fabric",
        provided_mods=(("flywheel", "1.0.0"),),
    )
    second = ModInfo(
        path=tmp_path / "ponderjs.jar",
        file_name="ponderjs.jar",
        enabled=True,
        mod_id="ponderjs",
        name="PonderJS",
        version="1.0.0",
        loader="fabric",
        provided_mods=(("flywheel", "1.0.0"),),
    )

    report = ModCompatibilityManager.scan(instance, mods=[first, second])

    assert not any(issue.code == "duplicate-mod-id" and "flywheel" in issue.mod_ids for issue in report.issues)


def test_duplicate_primary_mod_ids_remain_blocking_with_provided_capabilities(tmp_path) -> None:
    instance = make_instance(tmp_path)
    first = ModInfo(path=tmp_path / "first.jar", file_name="first.jar", enabled=True, mod_id="example", name="Example A", version="1.0.0", loader="fabric", provided_mods=(("shared", "1.0.0"),))
    second = ModInfo(path=tmp_path / "second.jar", file_name="second.jar", enabled=True, mod_id="example", name="Example B", version="2.0.0", loader="fabric", provided_mods=(("shared", "2.0.0"),))

    report = ModCompatibilityManager.scan(instance, mods=[first, second])

    duplicates = [issue for issue in report.issues if issue.code == "duplicate-mod-id"]
    assert len(duplicates) == 1
    assert duplicates[0].mod_ids == ("example",)


def test_detects_disabled_and_wrong_dependency_version(tmp_path, monkeypatch):
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance = make_instance(tmp_path)
    mods = instance.instance_dir / "mods"
    write_mod(mods / "library.jar", "library", version="1.0.0", enabled=False)
    write_mod(mods / "consumer.jar", "consumer", depends={"library": ">=2.0.0"})

    report = ModCompatibilityManager.scan(instance)

    assert any(issue.code == "dependency-disabled" for issue in report.issues)


def test_detects_breaks_declaration(tmp_path, monkeypatch):
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)
    instance = make_instance(tmp_path)
    mods = instance.instance_dir / "mods"
    write_mod(mods / "a.jar", "a", breaks={"b": "*"})
    write_mod(mods / "b.jar", "b")

    report = ModCompatibilityManager.scan(instance)

    assert any(issue.code == "breaks" and issue.severity == "error" for issue in report.issues)


def write_forge_mod(path: Path, mod_id: str, *, minecraft_range="[1.20.1,1.21)", forge_range="[47,)") -> Path:
    metadata = (
        'modLoader="javafml"\n'
        f'loaderVersion="{forge_range}"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        'version="1.0.0"\n'
        f'displayName="{mod_id}"\n\n'
        f'[[dependencies.{mod_id}]]\n'
        'modId="minecraft"\n'
        'mandatory=true\n'
        f'versionRange="{minecraft_range}"\n'
        'ordering="NONE"\n'
        'side="BOTH"\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)
    return path


def test_forge_maven_ranges_match_installed_versions(tmp_path):
    instance_dir = tmp_path / "forge-instance"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="forge", name="Forge", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.3.0"))
    write_forge_mod(mods / "consumer.jar", "consumer")

    report = ModCompatibilityManager.scan(instance)

    assert not any(issue.code == "dependency-version" for issue in report.issues)
    assert not any(issue.code == "loader-mismatch" for issue in report.issues)


def test_detects_loader_mismatch_for_manually_copied_mod(tmp_path):
    instance_dir = tmp_path / "forge-instance"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="forge", name="Forge", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.3.0"))
    write_mod(mods / "fabric.jar", "fabric_only")

    report = ModCompatibilityManager.scan(instance)

    assert any(issue.code == "loader-mismatch" for issue in report.issues)


def test_maven_range_rejects_outside_version() -> None:
    assert ModCompatibilityManager._matches_requirement("46.0.0", "[47,)") is False
    assert ModCompatibilityManager._matches_requirement("47.3.0", "[47,)") is True
    assert ModCompatibilityManager._matches_requirement("1.21.0", "[1.20.1,1.21)") is False


@pytest.mark.parametrize(
    ("installed", "required"),
    (
        ("3.0.1.10", "[3.0.1.7,)"),
        ("2.4-Fix", "[2.4,)"),
        ("1.20.1-1.5.2-neoforge", "[1.20.1,]"),
        ("1.20.1", "1.19,1.20.1,"),
    ),
)
def test_atm9_forge_version_requirements_match(installed: str, required: str) -> None:
    assert ModCompatibilityManager._matches_requirement(installed, required) is True


def test_comma_separated_comparator_constraints_remain_conjunctive() -> None:
    assert ModCompatibilityManager._matches_requirement("1.5.0", ">=1.0,<2.0") is True
    assert ModCompatibilityManager._matches_requirement("2.1.0", ">=1.0,<2.0") is False


def test_optional_recommendations_are_informational_not_launch_warnings(tmp_path) -> None:
    instance = make_instance(tmp_path)
    consumer = ModInfo(
        path=tmp_path / "consumer.jar",
        file_name="consumer.jar",
        enabled=True,
        mod_id="consumer",
        name="Consumer",
        version="1.0.0",
        loader="fabric",
        recommends={"optional_mod": "[1.0,)"},
    )

    report = ModCompatibilityManager.scan(instance, mods=[consumer])

    issue = next(issue for issue in report.issues if issue.code == "recommended-missing")
    assert issue.severity == "info"
    assert report.warning_count == 0


@pytest.mark.parametrize(
    ("installed", "required"),
    (
        ("1.19.2-3.0.0.6", "[1.19-3.0.0.3,)"),
        ("1.19.2-5.1.4.3", "[1.19-5.1.0.0,)"),
        ("1.8.2-55", "[1.8-54,)"),
        ("1.19.2-4.2.8", "[1.19-4.0.7,)"),
        ("1.19.2-4.2.18", "[1.19-4.0.12,)"),
    ),
)
def test_forge_mod_versions_used_by_existing_modpacks_match(installed: str, required: str) -> None:
    assert ModCompatibilityManager._matches_requirement(installed, required) is True


def test_pack_managed_dependency_version_mismatch_is_non_blocking(tmp_path) -> None:
    instance_dir = tmp_path / "pack-instance"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="pack", name="Pack", version_id="1.19.2", instance_dir=instance_dir, mod_loader=("forge", "43.4.0"))
    dependency = ModInfo(
        path=tmp_path / "curios.jar",
        file_name="curios.jar",
        enabled=True,
        mod_id="curios",
        name="Curios API",
        version="2.0.0",
        loader="forge",
        managed_by_modpack=True,
    )
    consumer = ModInfo(
        path=tmp_path / "elytra-slot.jar",
        file_name="elytra-slot.jar",
        enabled=True,
        mod_id="elytraslot",
        name="Elytra Slot",
        version="6.1.0",
        loader="forge",
        dependencies={"curios": "[3.0.0,)"},
        managed_by_modpack=True,
    )

    report = ModCompatibilityManager.scan(instance, mods=[dependency, consumer])

    assert not any(issue.code == "dependency-version" for issue in report.issues)
    assert any(issue.code == "pack-pinned-dependency-requirement" and issue.severity == "warning" for issue in report.issues)


def test_manual_dependency_version_mismatch_remains_blocking(tmp_path) -> None:
    instance_dir = tmp_path / "manual-instance"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="manual", name="Manual", version_id="1.19.2", instance_dir=instance_dir, mod_loader=("forge", "43.4.0"))
    dependency = ModInfo(
        path=tmp_path / "curios.jar",
        file_name="curios.jar",
        enabled=True,
        mod_id="curios",
        name="Curios API",
        version="2.0.0",
        loader="forge",
        managed_by_modpack=False,
    )
    consumer = ModInfo(
        path=tmp_path / "elytra-slot.jar",
        file_name="elytra-slot.jar",
        enabled=True,
        mod_id="elytraslot",
        name="Elytra Slot",
        version="6.1.0",
        loader="forge",
        dependencies={"curios": "[3.0.0,)"},
        managed_by_modpack=True,
    )

    report = ModCompatibilityManager.scan(instance, mods=[dependency, consumer])

    assert any(issue.code == "dependency-version" and issue.severity == "error" for issue in report.issues)

def test_neoforge_loader_dependency_matches_installed_version(tmp_path):
    instance_dir = tmp_path / "neoforge-instance"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="neoforge", name="NeoForge", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("neoforge", "21.1.200"))
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[21.1,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        'modId="consumer"\n'
        'version="1.0.0"\n'
        'displayName="consumer"\n'
    )
    with zipfile.ZipFile(mods / "consumer.jar", "w") as archive:
        archive.writestr("META-INF/neoforge.mods.toml", metadata)

    report = ModCompatibilityManager.scan(instance)

    assert not any(issue.code == "dependency-version" for issue in report.issues)
    assert not any(issue.code == "loader-mismatch" for issue in report.issues)




def test_neoforge_satisfies_legacy_forge_runtime_dependency_for_dual_loader_mod(tmp_path):
    instance_dir = tmp_path / "neoforge-e4mc"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="neoforge-e4mc", name="NeoForge e4mc", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("neoforge", "47.1.106"))
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        'modId="e4mc_minecraft"\n'
        'version="5.0.0"\n'
        'displayName="e4mc"\n\n'
        '[[dependencies.e4mc_minecraft]]\n'
        'modId="forge"\n'
        'mandatory=true\n'
        'versionRange="*"\n'
        'ordering="NONE"\n'
        'side="BOTH"\n'
    )
    with zipfile.ZipFile(mods / "e4mc.jar", "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)

    report = ModCompatibilityManager.scan(instance)

    assert not any(issue.code == "dependency-missing" and "forge" in issue.mod_ids for issue in report.issues)
    assert not any(issue.code == "loader-mismatch" for issue in report.issues)


def write_quilt_mod(path: Path, mod_id: str, *, depends=None) -> Path:
    metadata = {
        "schema_version": 1,
        "quilt_loader": {
            "group": "dev.mcw",
            "id": mod_id,
            "version": "1.0.0",
            "metadata": {"name": mod_id},
            "depends": depends or [],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("quilt.mod.json", json.dumps(metadata))
    return path


def test_quilt_runtime_satisfies_quilt_and_fabric_loader_dependencies(tmp_path):
    instance_dir = tmp_path / "quilt-instance"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="quilt", name="Quilt", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("quilt", "0.27.1"))
    write_quilt_mod(
        mods / "consumer.jar",
        "consumer",
        depends=[
            {"id": "quilt_loader", "versions": ">=0.20.0"},
            {"id": "fabricloader", "versions": "*"},
            {"id": "minecraft", "versions": "1.20.1"},
        ],
    )

    report = ModCompatibilityManager.scan(instance)

    assert not any(issue.code.startswith("dependency-") for issue in report.issues)
    assert not any(issue.code == "loader-mismatch" for issue in report.issues)


def test_quilt_instance_rejects_forge_only_mod(tmp_path):
    instance_dir = tmp_path / "quilt-forge-mismatch"
    mods = instance_dir / "mods"
    mods.mkdir(parents=True)
    instance = Instance(instance_id="quilt-forge", name="Quilt", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("quilt", "0.27.1"))
    write_forge_mod(mods / "forge-only.jar", "forge_only")

    report = ModCompatibilityManager.scan(instance)

    assert any(issue.code == "loader-mismatch" for issue in report.issues)


def test_jarjar_provided_mod_satisfies_required_dependency(tmp_path) -> None:
    instance_dir = tmp_path / "jarjar-instance"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="jarjar", name="JarJar", version_id="1.19.2", instance_dir=instance_dir, mod_loader=("forge", "43.4.0"))
    provider = ModInfo(
        path=instance_dir / "mods" / "kotlinforforge-3.9.1-all.jar",
        file_name="kotlinforforge-3.9.1-all.jar",
        enabled=True,
        mod_id="unknown",
        name="kotlinforforge-3.9.1-all",
        version="3.9.1",
        loader="forge",
        metadata_format="MANIFEST.MF:FMLModType=LIBRARY",
        provided_mods=(("kotlinforforge", "3.9.1"),),
        managed_by_modpack=True,
    )
    consumer = ModInfo(
        path=instance_dir / "mods" / "sliceanddice.jar",
        file_name="sliceanddice.jar",
        enabled=True,
        mod_id="sliceanddice",
        name="Create Slice & Dice",
        version="2.4.0",
        loader="forge",
        dependencies={"kotlinforforge": "[3.9.1,)"},
        managed_by_modpack=True,
    )

    report = ModCompatibilityManager.scan(instance, mods=[provider, consumer])

    assert not any(issue.code in {"dependency-missing", "dependency-version"} and "kotlinforforge" in issue.mod_ids for issue in report.issues)


def test_java_dependency_is_launcher_environment_capability(tmp_path) -> None:
    instance_dir = tmp_path / "java-capability"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="java-capability", name="Java Capability", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47.3.0"))
    consumer = ModInfo(
        path=instance_dir / "mods" / "consumer.jar",
        file_name="consumer.jar",
        enabled=True,
        mod_id="consumer",
        name="Consumer",
        version="1.0.0",
        loader="forge",
        dependencies={"java": "[17,)"},
    )

    report = ModCompatibilityManager.scan(instance, mods=[consumer])

    assert not any(issue.code.startswith("dependency-") and "java" in issue.mod_ids for issue in report.issues)


def test_active_fabric_loader_alias_is_environment_capability(tmp_path) -> None:
    instance_dir = tmp_path / "fabric-capability"
    (instance_dir / "mods").mkdir(parents=True)
    instance = Instance(instance_id="fabric-capability", name="Fabric Capability", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))
    consumer = ModInfo(
        path=instance_dir / "mods" / "consumer.jar",
        file_name="consumer.jar",
        enabled=True,
        mod_id="consumer",
        name="Consumer",
        version="1.0.0",
        loader="fabric",
        dependencies={"fabric": ">=0.15.0"},
    )

    report = ModCompatibilityManager.scan(instance, mods=[consumer])

    assert not any(issue.code.startswith("dependency-") and "fabric" in issue.mod_ids for issue in report.issues)


def test_forge_parser_does_not_promote_other_mod_dependency_group(tmp_path) -> None:
    from src.core.mod.mod_manager import ModManager

    path = tmp_path / "multi-component.jar"
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        'modId="primary"\n'
        'version="1.0.0"\n'
        'displayName="Primary"\n\n'
        '[[dependencies.secondary]]\n'
        'modId="fabricloader"\n'
        'mandatory=true\n'
        'versionRange="[0.15,)"\n'
        'ordering="NONE"\n'
        'side="BOTH"\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)

    mod = ModManager.read_mod(path, preferred_loader="forge")

    assert mod.mod_id == "primary"
    assert "fabricloader" not in mod.dependencies
    assert mod.dependencies["forge"] == "[47,)"
