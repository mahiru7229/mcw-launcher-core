import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.modloader.forge.forge_launch_command_manager import ForgeLaunchCommandManager


def make_version(*, modern: bool = True, loader: str = "forge"):
    metadata = {loader: {"loaderVersion": "21.1.200" if loader == "neoforge" else "47.4.21"}} if modern else {}
    return SimpleNamespace(
        main_class=(
            "cpw.mods.bootstraplauncher.BootstrapLauncher"
            if modern
            else "net.minecraft.client.main.Main"
        ),
        raw_json=metadata,
    )


def make_module_path(tmp_path: Path) -> str:
    bootstrap = tmp_path / "bootstraplauncher.jar"
    securejarhandler = tmp_path / "securejarhandler.jar"
    bootstrap.write_bytes(b"bootstrap")
    securejarhandler.write_bytes(b"secure")
    return os.pathsep.join((str(bootstrap), str(securejarhandler)))


def test_prepare_normalizes_short_module_path_flag(tmp_path: Path) -> None:
    module_path = make_module_path(tmp_path)

    result = ForgeLaunchCommandManager.prepare(
        make_version(),
        [
            "-p",
            module_path,
            "--add-modules",
            "ALL-MODULE-PATH",
            "--add-opens",
            "java.base/java.lang.invoke=cpw.mods.securejarhandler",
        ],
    )

    assert result[:4] == [
        "--module-path",
        module_path,
        "--add-modules",
        "ALL-MODULE-PATH",
    ]


def test_prepare_adds_all_module_path_when_profile_omits_it(tmp_path: Path) -> None:
    module_path = make_module_path(tmp_path)

    result = ForgeLaunchCommandManager.prepare(
        make_version(),
        ["--module-path", module_path, "-Dforge=true"],
    )

    assert result[:5] == [
        "--module-path",
        module_path,
        "--add-modules",
        "ALL-MODULE-PATH",
        "-Dforge=true",
    ]
    assert any(value.startswith("-DignoreList=") for value in result)


def test_prepare_accepts_inline_module_path(tmp_path: Path) -> None:
    module_path = make_module_path(tmp_path)

    result = ForgeLaunchCommandManager.prepare(
        make_version(),
        [
            f"--module-path={module_path}",
            "--add-modules=ALL-MODULE-PATH",
        ],
    )

    assert result[:2] == [
        f"--module-path={module_path}",
        "--add-modules=ALL-MODULE-PATH",
    ]
    assert any(value.startswith("-DignoreList=") for value in result)


def test_prepare_rejects_unresolved_forge_placeholders() -> None:
    with pytest.raises(RuntimeError, match="unresolved launcher placeholders"):
        ForgeLaunchCommandManager.prepare(
            make_version(),
            [
                "-p",
                "${library_directory}/securejarhandler.jar",
                "--add-modules",
                "ALL-MODULE-PATH",
            ],
        )


def test_prepare_reports_missing_module_path_libraries(tmp_path: Path) -> None:
    module_path = os.pathsep.join(
        (
            str(tmp_path / "bootstraplauncher.jar"),
            str(tmp_path / "securejarhandler.jar"),
        )
    )

    with pytest.raises(RuntimeError, match="required module-path libraries are missing"):
        ForgeLaunchCommandManager.prepare(
            make_version(),
            ["--module-path", module_path],
        )


def test_prepare_requires_module_path_for_modern_forge() -> None:
    with pytest.raises(RuntimeError, match="does not define a module path"):
        ForgeLaunchCommandManager.prepare(
            make_version(),
            ["--add-opens", "java.base/java.lang.invoke=cpw.mods.securejarhandler"],
        )



def test_prepare_adds_certificate_compatibility_property_for_legacy_forge() -> None:
    version = SimpleNamespace(
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={"forge": {"gameVersion": "1.6.4", "loaderVersion": "9.11.1.1345"}},
    )

    result = ForgeLaunchCommandManager.prepare(version, ["-Xmx2G"])

    assert result == ["-Xmx2G", "-Dfml.ignoreInvalidMinecraftCertificates=true"]


def test_prepare_normalizes_conflicting_legacy_certificate_property() -> None:
    version = SimpleNamespace(
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={"forge": {"gameVersion": "1.6.4", "loaderVersion": "9.11.1.1345"}},
    )

    result = ForgeLaunchCommandManager.prepare(
        version,
        [
            "-Dfml.ignoreInvalidMinecraftCertificates=false",
            "-Xmx2G",
            "-Dfml.ignoreInvalidMinecraftCertificates=true",
        ],
    )

    assert result == ["-Dfml.ignoreInvalidMinecraftCertificates=true", "-Xmx2G"]


def test_prepare_does_not_bypass_certificates_for_non_forge_launchwrapper() -> None:
    version = SimpleNamespace(
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={},
    )
    arguments = ["-Xmx2G"]

    assert ForgeLaunchCommandManager.prepare(version, arguments) == arguments

def test_prepare_leaves_non_forge_arguments_unchanged() -> None:
    arguments = ["-Xmx2G", "-cp", "minecraft.jar"]

    assert ForgeLaunchCommandManager.prepare(make_version(modern=False), arguments) == arguments


def test_prepare_removes_minecraft_client_from_module_path_and_ignores_it(tmp_path: Path) -> None:
    libraries = tmp_path / "libraries"
    versions = tmp_path / "versions" / "1.20.1"
    libraries.mkdir()
    versions.mkdir(parents=True)

    bootstrap = libraries / "bootstraplauncher.jar"
    securejarhandler = libraries / "securejarhandler.jar"
    client = versions / "1.20.1.jar"
    bootstrap.write_bytes(b"bootstrap")
    securejarhandler.write_bytes(b"secure")
    client.write_bytes(b"minecraft")

    version = make_version()
    version.raw_json["inheritsFrom"] = "1.20.1"
    module_path = os.pathsep.join((str(bootstrap), str(client), str(securejarhandler)))

    result = ForgeLaunchCommandManager.prepare(
        version,
        ["--module-path", module_path, "-DignoreList=bootstraplauncher,forge-1.20.1-47.4.22.jar"],
        client_path=client,
        library_directory=libraries,
    )

    module_path_index = result.index("--module-path")
    sanitized_entries = result[module_path_index + 1].split(os.pathsep)
    assert sanitized_entries == [str(bootstrap), str(securejarhandler)]

    ignore_list = next(value for value in result if value.startswith("-DignoreList="))
    assert "1.20.1.jar" in ignore_list.split("=", 1)[1].split(",")
    assert f"-DlibraryDirectory={libraries}" in result


def test_prepare_adds_default_ignore_list_when_profile_omits_it(tmp_path: Path) -> None:
    module_path = make_module_path(tmp_path)
    client = tmp_path / "versions" / "1.20.1" / "1.20.1.jar"
    client.parent.mkdir(parents=True)
    client.write_bytes(b"minecraft")
    version = make_version()
    version.raw_json["inheritsFrom"] = "1.20.1"

    result = ForgeLaunchCommandManager.prepare(
        version,
        ["--module-path", module_path],
        client_path=client,
    )

    ignore_list = next(value for value in result if value.startswith("-DignoreList="))
    values = ignore_list.split("=", 1)[1].split(",")
    assert "securejarhandler" in values
    assert "JarJarFileSystems" in values
    assert "1.20.1.jar" in values


def test_prepare_supports_modern_neoforge_profile(tmp_path: Path) -> None:
    module_path = make_module_path(tmp_path)

    result = ForgeLaunchCommandManager.prepare(make_version(loader="neoforge"), ["--module-path", module_path])

    assert "--add-modules" in result
    ignore_list = next(value for value in result if value.startswith("-DignoreList="))
    assert "neoforge-" in ignore_list
    assert "mixinextras-neoforge" in ignore_list
    assert ForgeLaunchCommandManager.is_modern_forge(make_version(loader="neoforge"))


def test_neoforge_error_message_names_neoforge() -> None:
    with pytest.raises(RuntimeError, match="NeoForge launch profile"):
        ForgeLaunchCommandManager.prepare(make_version(loader="neoforge"), [])
