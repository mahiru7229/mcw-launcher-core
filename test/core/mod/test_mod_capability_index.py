from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import zipfile

from src.core.mod.mod_capability_index import ModCapabilityIndex
from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.core.mod.mod_manager import ModManager
from src.models.instance.instance import Instance


def forge_instance(tmp_path: Path, version: str = "1.19.2") -> Instance:
    instance_dir = tmp_path / "Forge Pack"
    (instance_dir / "mods").mkdir(parents=True)
    return Instance(instance_id="forge-pack", name="Forge Pack", version_id=version, instance_dir=instance_dir, mod_loader=("forge", "43.4.0"))


def forge_jar_bytes(mod_id: str, version: str, dependencies: dict[str, str] | None = None) -> bytes:
    lines = [
        'modLoader="javafml"',
        'loaderVersion="[40,)"',
        'license="MIT"',
        '',
        '[[mods]]',
        f'modId="{mod_id}"',
        f'version="{version}"',
        f'displayName="{mod_id}"',
    ]
    for dependency_id, requirement in (dependencies or {}).items():
        lines.extend([
            '',
            f'[[dependencies.{mod_id}]]',
            f'modId="{dependency_id}"',
            'mandatory=true',
            f'versionRange="{requirement}"',
            'ordering="NONE"',
            'side="BOTH"',
        ])
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/mods.toml", "\n".join(lines) + "\n")
    return output.getvalue()


def write_forge_jar(path: Path, mod_id: str, version: str, dependencies: dict[str, str] | None = None) -> Path:
    path.write_bytes(forge_jar_bytes(mod_id, version, dependencies))
    return path


def write_jarjar_owner(path: Path, owner_id: str, owner_version: str, nested_name: str, nested_bytes: bytes, dependencies: dict[str, str] | None = None, library_outer: bool = False) -> Path:
    owner_bytes = forge_jar_bytes(owner_id, owner_version, dependencies)
    with zipfile.ZipFile(BytesIO(owner_bytes), "r") as source:
        owner_entries = {name: source.read(name) for name in source.namelist()}

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in owner_entries.items():
            archive.writestr(name, raw)
        nested_path = f"META-INF/jarjar/{nested_name}"
        archive.writestr(nested_path, nested_bytes)
        archive.writestr(
            "META-INF/jarjar/metadata.json",
            json.dumps({"jars": [{"identifier": {"group": "test", "artifact": nested_name.removesuffix('.jar')}, "version": {"range": "[0,)", "artifactVersion": "1"}, "path": nested_path}]}),
        )
        if library_outer:
            archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nFMLModType: LIBRARY\nImplementation-Version: 3.12.0\n")
    return path


def test_embedded_flywheel_satisfies_create_dependency_ranges(tmp_path):
    instance = forge_instance(tmp_path)
    mods = Path(instance.instance_dir) / "mods"
    flywheel = forge_jar_bytes("flywheel", "0.6.10")
    write_jarjar_owner(
        mods / "create.jar",
        "create",
        "0.5.1",
        "flywheel.jar",
        flywheel,
        dependencies={"flywheel": "[0.6.10,0.6.11)"},
    )
    write_forge_jar(
        mods / "createaddition.jar",
        "createaddition",
        "1.2.3",
        dependencies={"flywheel": "[0.6.8.a,0.7)"},
    )

    report = ModCompatibilityManager.scan(instance)
    capabilities = ModCapabilityIndex.build(instance)

    assert capabilities["flywheel"][0].source == "embedded"
    assert capabilities["flywheel"][0].version == "0.6.10"
    assert not any(issue.code.startswith("dependency-") and "flywheel" in issue.mod_ids for issue in report.issues)


def test_nested_kotlinforforge_language_bundle_satisfies_mod_dependency(tmp_path):
    instance = forge_instance(tmp_path)
    mods = Path(instance.instance_dir) / "mods"
    write_forge_jar(
        mods / "sliceanddice.jar",
        "sliceanddice",
        "2.3.0",
        dependencies={"kotlinforforge": "[3.9.1,)"},
    )
    kff_mod = forge_jar_bytes("kotlinforforge", "3.12.0")
    write_jarjar_owner(
        mods / "kotlinforforge-all.jar",
        "kotlinforforge_bundle",
        "3.12.0",
        "kffmod-forge.jar",
        kff_mod,
        library_outer=True,
    )

    report = ModCompatibilityManager.scan(instance)

    assert not any(issue.code.startswith("dependency-") and "kotlinforforge" in issue.mod_ids for issue in report.issues)


def test_forge_style_version_with_letter_component_matches_maven_range():
    assert ModCompatibilityManager._matches_requirement("0.6.10", "[0.6.8.a,0.7)") is True
    assert ModCompatibilityManager._matches_requirement("0.6.8.a", "[0.6.8.a,0.7)") is True
    assert ModCompatibilityManager._matches_requirement("0.7.0", "[0.6.8.a,0.7)") is False


def test_atm9_artifacts_embedded_expandability_satisfies_dependency_without_standalone_jar(tmp_path):
    instance = forge_instance(tmp_path, version="1.20.1")
    instance.mod_loader = ("forge", "47.4.0")
    mods = Path(instance.instance_dir) / "mods"
    nested = forge_jar_bytes("expandability", "9.0.4")
    owner_bytes = forge_jar_bytes("artifacts", "9.5.13", {"expandability": "[9.0.0,)"})
    owner = mods / "artifacts-forge-9.5.13.jar"

    with zipfile.ZipFile(BytesIO(owner_bytes), "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}
    with zipfile.ZipFile(owner, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
        # Some Forge JarJar artifacts are recoverable from the standard jarjar
        # directory even when metadata.json does not enumerate the nested JAR.
        archive.writestr("META-INF/jarjar/expandability-9.0.4.jar", nested)

    listed = ModManager.list_mods(instance)
    capabilities = ModCapabilityIndex.build(instance, listed)
    report = ModCompatibilityManager.scan(instance, mods=listed)

    assert not (mods / "expandability-9.0.4.jar").exists()
    assert listed[0].provided_mods == ()
    assert capabilities["expandability"][0].source == "embedded"
    assert capabilities["expandability"][0].version == "9.0.4"
    assert not any(issue.code.startswith("dependency-") and "expandability" in issue.mod_ids for issue in report.issues)


def test_embedded_dependency_version_is_still_validated(tmp_path):
    instance = forge_instance(tmp_path, version="1.20.1")
    instance.mod_loader = ("forge", "47.4.0")
    mods = Path(instance.instance_dir) / "mods"
    nested = forge_jar_bytes("expandability", "8.9.0")
    owner_bytes = forge_jar_bytes("artifacts", "9.5.13", {"expandability": "[9.0.0,)"})
    owner = mods / "artifacts-forge-9.5.13.jar"

    with zipfile.ZipFile(BytesIO(owner_bytes), "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}
    with zipfile.ZipFile(owner, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
        archive.writestr("META-INF/jarjar/expandability-8.9.0.jar", nested)

    report = ModCompatibilityManager.scan(instance)

    assert any(issue.code == "dependency-version" and "expandability" in issue.mod_ids for issue in report.issues)
