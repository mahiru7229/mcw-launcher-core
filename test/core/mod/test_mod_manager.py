from pathlib import Path
import json
import zipfile

import pytest

from src.core.instance.errors import InstanceModChangeBlockedError
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path, loader=("fabric", "0.19.3")) -> Instance:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    return Instance(instance_id="instance-id", name="Test", version_id="1.20.1", instance_dir=instance_dir, mod_loader=loader)


def make_mod(path: Path, mod_id="example", name="Example Mod", version="1.0.0") -> Path:
    metadata = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": name,
        "version": version,
        "description": "A test Fabric mod.",
        "environment": "client",
        "authors": ["Mahiru"],
        "license": "MIT",
        "depends": {"fabricloader": ">=0.15.0", "minecraft": "1.20.1"},
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(metadata))
    return path


@pytest.fixture(autouse=True)
def unlocked(monkeypatch):
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda instance: False)


def test_add_scan_disable_enable_and_remove_mod(tmp_path):
    instance = make_instance(tmp_path)
    source = make_mod(tmp_path / "example.jar")

    added = ModManager.add_mods(instance, [source])
    scanned = ModManager.list_mods(instance)

    assert added[0].mod_id == "example"
    assert scanned[0].enabled is True
    assert scanned[0].dependencies["minecraft"] == "1.20.1"

    disabled = ModManager.set_enabled(instance, [scanned[0].path], False)
    assert disabled[0].enabled is False
    assert disabled[0].path.name.endswith(".jar.disabled")

    enabled = ModManager.set_enabled(instance, [disabled[0].path], True)
    assert enabled[0].enabled is True

    ModManager.remove_mods(instance, [enabled[0].path])
    assert ModManager.list_mods(instance) == []


def test_rejects_non_fabric_jar(tmp_path):
    instance = make_instance(tmp_path)
    source = tmp_path / "other.jar"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0")

    with pytest.raises(RuntimeError, match="fabric.mod.json"):
        ModManager.add_mods(instance, [source])


def test_rejects_mod_changes_for_vanilla_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("vanilla", "-1"))
    source = make_mod(tmp_path / "example.jar")

    with pytest.raises(RuntimeError, match="does not use Fabric"):
        ModManager.add_mods(instance, [source])


def test_blocks_mod_changes_while_instance_is_running(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    source = make_mod(tmp_path / "example.jar")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda current: True)

    with pytest.raises(InstanceModChangeBlockedError):
        ModManager.add_mods(instance, [source])


def test_replace_same_mod_file_does_not_delete_source(tmp_path):
    instance = make_instance(tmp_path)
    source = make_mod(tmp_path / "example.jar")
    installed = ModManager.add_mods(instance, [source])[0]

    replaced = ModManager.add_mods(instance, [installed.path], replace=True)

    assert installed.path.exists()
    assert replaced[0].mod_id == "example"


def make_forge_mod(path: Path, mod_id="forge_example", name="Forge Example", version="1.0.0") -> Path:
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        f'version="{version}"\n'
        f'displayName="{name}"\n'
        'authors="Mahiru"\n'
        'description="A Forge test mod."\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)
    return path


def test_adds_and_reads_forge_mod(tmp_path):
    instance = make_instance(tmp_path, loader=("forge", "47.3.0"))
    source = make_forge_mod(tmp_path / "forge-example.jar")

    added = ModManager.add_mods(instance, [source])

    assert added[0].mod_id == "forge_example"
    assert added[0].name == "Forge Example"
    assert added[0].version == "1.0.0"
    assert added[0].status == "Ready"


def make_forge_mod_with_dependencies(path: Path, mod_id="forge_consumer", version="1.0.0") -> Path:
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        f'version="{version}"\n'
        'displayName="Forge Consumer"\n'
        'authors="Mahiru, Tester"\n'
        'description="Forge dependency test."\n\n'
        f'[[dependencies.{mod_id}]]\n'
        'modId="minecraft"\n'
        'mandatory=true\n'
        'versionRange="[1.20.1,1.21)"\n'
        'ordering="NONE"\n'
        'side="BOTH"\n\n'
        f'[[dependencies.{mod_id}]]\n'
        'modId="librarymod"\n'
        'mandatory=false\n'
        'versionRange="[2.0,)"\n'
        'ordering="AFTER"\n'
        'side="BOTH"\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)
    return path


def make_legacy_forge_mod(path: Path) -> Path:
    metadata = [
        {
            "modid": "legacy_example",
            "name": "Legacy Example",
            "version": "1.0.0",
            "mcversion": "1.8.9",
            "description": "A legacy Forge test mod.",
            "authorList": ["Mahiru"],
            "requiredMods": ["required-after:legacy_library@[1.0,)"]
        }
    ]
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mcmod.info", json.dumps(metadata))
    return path


def test_reads_forge_dependencies_and_loader_requirement(tmp_path):
    source = make_forge_mod_with_dependencies(tmp_path / "forge-consumer.jar")

    mod = ModManager.read_mod(source)

    assert mod.loader == "forge"
    assert mod.metadata_format == "mods.toml"
    assert mod.dependencies["forge"] == "[47,)"
    assert mod.dependencies["minecraft"] == "[1.20.1,1.21)"
    assert mod.recommends["librarymod"] == "[2.0,)"
    assert mod.authors == ("Mahiru", "Tester")


def test_reads_legacy_forge_mcmod_info(tmp_path):
    source = make_legacy_forge_mod(tmp_path / "legacy.jar")

    mod = ModManager.read_mod(source)

    assert mod.loader == "forge"
    assert mod.metadata_format == "mcmod.info"
    assert mod.mod_id == "legacy_example"
    assert mod.dependencies["minecraft"] == "1.8.9"
    assert mod.dependencies["legacy_library"] == "[1.0,)"


def test_rejects_wrong_loader_mod(tmp_path):
    instance = make_instance(tmp_path, loader=("forge", "47.3.0"))
    source = make_mod(tmp_path / "fabric-only.jar")

    with pytest.raises(RuntimeError, match="Fabric mod"):
        ModManager.add_mods(instance, [source])


def test_rejects_duplicate_mod_id_with_different_filename(tmp_path):
    instance = make_instance(tmp_path, loader=("forge", "47.3.0"))
    ModManager.add_mods(instance, [make_forge_mod(tmp_path / "first.jar", mod_id="duplicate")])

    with pytest.raises(FileExistsError, match="Mod ID 'duplicate'"):
        ModManager.add_mods(instance, [make_forge_mod(tmp_path / "second.jar", mod_id="duplicate")])


def test_launch_preparation_token_allows_managed_mod_install(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    source = make_mod(tmp_path / "managed.jar", mod_id="managed")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda current: True)
    monkeypatch.setattr(InstanceRunLock, "owns_preparing_lock", lambda current, token: token == "owned-token")

    added = ModManager.add_mods(instance, [source], launch_lock_token="owned-token")

    assert added[0].mod_id == "managed"


def test_wrong_launch_preparation_token_still_blocks_mod_install(tmp_path, monkeypatch):
    instance = make_instance(tmp_path)
    source = make_mod(tmp_path / "managed.jar", mod_id="managed")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda current: True)
    monkeypatch.setattr(InstanceRunLock, "owns_preparing_lock", lambda current, token: False)

    with pytest.raises(InstanceModChangeBlockedError):
        ModManager.add_mods(instance, [source], launch_lock_token="wrong-token")


def make_universal_fabric_forge_mod(path: Path, mod_id="universal_example") -> Path:
    fabric_metadata = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": "Universal Fabric View",
        "version": "1.0.0",
        "environment": "client",
        "depends": {"fabricloader": ">=0.15.0", "minecraft": "1.20.1"},
    }
    forge_metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        f'modId="{mod_id}"\n'
        'version="1.0.0"\n'
        'displayName="Universal Forge View"\n'
        'description="A dual-loader test mod."\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(fabric_metadata))
        archive.writestr("META-INF/mods.toml", forge_metadata)
    return path


def test_read_mod_marks_dual_metadata_jar_as_universal_without_instance_context(tmp_path):
    source = make_universal_fabric_forge_mod(tmp_path / "universal.jar")

    mod = ModManager.read_mod(source)

    assert mod.loader == "universal"
    assert mod.metadata_format == "fabric.mod.json + mods.toml"
    assert mod.mod_id == "universal_example"


def test_dual_metadata_jar_uses_forge_metadata_in_forge_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("forge", "47.3.0"))
    source = make_universal_fabric_forge_mod(tmp_path / "universal.jar")

    added = ModManager.add_mods(instance, [source])

    assert added[0].loader == "forge"
    assert added[0].name == "Universal Forge View"
    assert added[0].dependencies["forge"] == "[47,)"
    assert "fabricloader" not in added[0].dependencies


def test_dual_metadata_jar_uses_fabric_metadata_in_fabric_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("fabric", "0.16.0"))
    source = make_universal_fabric_forge_mod(tmp_path / "universal.jar")

    added = ModManager.add_mods(instance, [source])

    assert added[0].loader == "fabric"
    assert added[0].name == "Universal Fabric View"
    assert added[0].dependencies["fabricloader"] == ">=0.15.0"


def test_reads_forge_language_provider_from_manifest(tmp_path):
    source = tmp_path / "kotlinforforge.jar"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\nFMLModType: LANGPROVIDER\nImplementation-Version: 3.12.0\n",
        )

    mod = ModManager.read_mod(source, preferred_loader="forge")

    assert mod.loader == "forge"
    assert mod.status == "Ready"
    assert mod.version == "3.12.0"
    assert "LANGPROVIDER" in mod.metadata_format


def test_reads_fml_managed_library_as_neoforge_for_neoforge_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("neoforge", "47.1.106"))
    source = tmp_path / "kotlinforforge-4.12.0-all.jar"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\nFMLModType: LIBRARY\n",
        )

    metadata = ModManager.read_mod(source, preferred_loader="neoforge", provider_version="4.12.0")
    ModManager.validate_mod_for_instance(instance, metadata)
    added = ModManager.add_mods(instance, [source])

    assert metadata.loader == "neoforge"
    assert metadata.version == "4.12.0"
    assert metadata.description == "Neoforge managed library"
    assert added[0].loader == "neoforge"
    assert added[0].status == "Ready"


def test_fml_managed_library_defaults_to_forge_without_family_preference(tmp_path):
    source = tmp_path / "forge-library.jar"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\nFMLModType: LIBRARY\nImplementation-Version: 1.2.3\n",
        )

    mod = ModManager.read_mod(source)

    assert mod.loader == "forge"
    assert mod.version == "1.2.3"


def test_allow_unverified_installs_fabric_jar_into_forge_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("forge", "47.3.0"))
    source = make_mod(tmp_path / "fabric-api-port.jar")

    added = ModManager.add_mods(instance, [source], allow_unverified=True)

    assert added[0].loader == "fabric"
    assert (ModManager.mods_dir(instance) / source.name).is_file()


def make_forge_placeholder_mod(path: Path, version: str, manifest: str = "", extra_properties: str = "") -> Path:
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[47,)"\n'
        'license="MIT"\n'
        f'{extra_properties}\n'
        '[[mods]]\n'
        'modId="placeholder_example"\n'
        f'version="{version}"\n'
        'displayName="Placeholder Example"\n'
        'description="Version placeholder test."\n'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/mods.toml", metadata)
        if manifest:
            archive.writestr("META-INF/MANIFEST.MF", manifest)
    return path


def test_resolves_file_jar_version_from_manifest(tmp_path):
    source = make_forge_placeholder_mod(
        tmp_path / "flywheel.jar",
        "${file.jarVersion}",
        "Manifest-Version: 1.0\nImplementation-Version: 0.6.8\n",
    )

    mod = ModManager.read_mod(source)

    assert mod.version == "0.6.8"


def test_resolves_jar_version_with_case_insensitive_continued_manifest_attribute(tmp_path):
    source = make_forge_placeholder_mod(
        tmp_path / "continued.jar",
        "${file.jarVersion}",
        "Manifest-Version: 1.0\niMpLeMeNtAtIoN-vErSiOn: 0.6.\n 8\n",
    )

    mod = ModManager.read_mod(source)

    assert mod.version == "0.6.8"


def test_resolves_generic_file_property_from_mod_metadata(tmp_path):
    source = make_forge_placeholder_mod(tmp_path / "property.jar", "${file.someKey}", extra_properties='someKey="2.4.1"')

    mod = ModManager.read_mod(source)

    assert mod.version == "2.4.1"


def test_uses_provider_version_when_placeholder_cannot_be_resolved(tmp_path):
    source = make_forge_placeholder_mod(tmp_path / "provider.jar", "${file.jarVersion}")

    mod = ModManager.read_mod(source, provider_version="3.1.4")

    assert mod.version == "3.1.4"


def test_infers_version_from_filename_after_placeholder_fallbacks(tmp_path):
    source = make_forge_placeholder_mod(tmp_path / "flywheel-forge-0.6.8.jar", "${file.jarVersion}")

    mod = ModManager.read_mod(source)

    assert mod.version == "0.6.8"


def test_unresolved_version_placeholder_becomes_unknown(tmp_path):
    source = make_forge_placeholder_mod(tmp_path / "flywheel.jar", "${file.jarVersion}")

    mod = ModManager.read_mod(source)

    assert mod.version == "Unknown"


def test_reads_legacy_mods_toml_as_neoforge_for_neoforge_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("neoforge", "47.1.106"))
    source = make_forge_mod(tmp_path / "legacy-neoforge.jar", mod_id="legacy_neoforge")

    added = ModManager.add_mods(instance, [source])

    assert added[0].loader == "neoforge"
    assert added[0].metadata_format == "mods.toml"
    assert added[0].mod_id == "legacy_neoforge"

def test_reads_modern_neoforge_metadata_and_dependencies(tmp_path):
    instance = make_instance(tmp_path, loader=("neoforge", "21.1.200"))
    source = tmp_path / "modern-neoforge.jar"
    metadata = (
        'modLoader="javafml"\n'
        'loaderVersion="[4,)"\n'
        'license="MIT"\n\n'
        '[[mods]]\n'
        'modId="modern_neoforge"\n'
        'version="1.2.3"\n'
        'displayName="Modern NeoForge"\n\n'
        '[[dependencies.modern_neoforge]]\n'
        'modId="minecraft"\n'
        'type="required"\n'
        'versionRange="[1.21.1,1.22)"\n'
        'ordering="NONE"\n'
        'side="BOTH"\n'
    )
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("META-INF/neoforge.mods.toml", metadata)

    added = ModManager.add_mods(instance, [source])

    assert added[0].loader == "neoforge"
    assert added[0].metadata_format == "neoforge.mods.toml"
    assert added[0].mod_id == "modern_neoforge"
    assert added[0].version == "1.2.3"
    assert added[0].dependencies["neoforge"] == "[4,)"
    assert added[0].dependencies["minecraft"] == "[1.21.1,1.22)"



def make_quilt_mod(path: Path, mod_id="quilt_example", name="Quilt Example", version="1.0.0") -> Path:
    metadata = {
        "schema_version": 1,
        "quilt_loader": {
            "group": "dev.mcw",
            "id": mod_id,
            "version": version,
            "metadata": {
                "name": name,
                "description": "A Quilt test mod.",
                "contributors": {"Mahiru": "Owner"},
                "license": "MIT",
            },
            "depends": [
                {"id": "quilt_loader", "versions": ">=0.20.0"},
                {"id": "minecraft", "versions": "1.20.1"},
            ],
            "recommends": {"qsl": "*"},
        },
        "minecraft": {"environment": "client"},
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("quilt.mod.json", json.dumps(metadata))
    return path


def test_adds_and_reads_quilt_mod(tmp_path):
    instance = make_instance(tmp_path, loader=("quilt", "0.27.1"))
    source = make_quilt_mod(tmp_path / "quilt-example.jar")

    added = ModManager.add_mods(instance, [source])

    assert added[0].mod_id == "quilt_example"
    assert added[0].name == "Quilt Example"
    assert added[0].loader == "quilt"
    assert added[0].metadata_format == "quilt.mod.json"
    assert added[0].dependencies["quilt_loader"] == ">=0.20.0"
    assert added[0].dependencies["minecraft"] == "1.20.1"
    assert added[0].recommends["qsl"] == "*"
    assert added[0].authors == ("Mahiru",)


def test_fabric_mod_is_read_as_quilt_compatible_in_quilt_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("quilt", "0.27.1"))
    source = make_mod(tmp_path / "fabric-compatible.jar")

    added = ModManager.add_mods(instance, [source])

    assert added[0].loader == "quilt"
    assert added[0].metadata_format == "fabric.mod.json (Quilt compatibility)"
    assert added[0].dependencies["fabricloader"] == ">=0.15.0"


def test_quilt_mod_is_rejected_by_fabric_instance(tmp_path):
    instance = make_instance(tmp_path, loader=("fabric", "0.16.0"))
    source = make_quilt_mod(tmp_path / "quilt-only.jar")

    with pytest.raises(RuntimeError, match="Quilt mod"):
        ModManager.add_mods(instance, [source])


def test_dual_quilt_and_fabric_metadata_prefers_instance_loader(tmp_path):
    path = tmp_path / "dual-quilt-fabric.jar"
    fabric = {
        "schemaVersion": 1,
        "id": "dual_example",
        "name": "Fabric View",
        "version": "1.0.0",
        "depends": {"fabricloader": "*"},
    }
    quilt = {
        "schema_version": 1,
        "quilt_loader": {
            "group": "dev.mcw",
            "id": "dual_example",
            "version": "1.0.0",
            "metadata": {"name": "Quilt View"},
            "depends": [{"id": "quilt_loader", "versions": "*"}],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(fabric))
        archive.writestr("quilt.mod.json", json.dumps(quilt))

    quilt_mod = ModManager.read_mod(path, preferred_loader="quilt")
    fabric_mod = ModManager.read_mod(path, preferred_loader="fabric")

    assert quilt_mod.loader == "quilt"
    assert quilt_mod.name == "Quilt View"
    assert fabric_mod.loader == "fabric"
    assert fabric_mod.name == "Fabric View"
