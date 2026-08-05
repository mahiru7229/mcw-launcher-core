from pathlib import Path
import json
import zipfile

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.models.instance.instance import Instance


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
