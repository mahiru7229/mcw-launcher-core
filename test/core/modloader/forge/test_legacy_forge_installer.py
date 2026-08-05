from __future__ import annotations

from pathlib import Path
import hashlib
import json
import zipfile

import pytest

from src.core.modloader.forge.legacy_forge_installer import LegacyForgeInstaller


FORGE_COORDINATE = "net.minecraftforge:forge:1.8.9-11.15.1.2318-1.8.9:universal"
FORGE_FILE = "forge-1.8.9-11.15.1.2318-1.8.9-universal.jar"
FORGE_PATH = f"net/minecraftforge/forge/1.8.9-11.15.1.2318-1.8.9/{FORGE_FILE}"
PROFILE_ID = "1.8.9-Forge11.15.1.2318-1.8.9"


def create_legacy_installer(path: Path, *, embedded_name: str = FORGE_FILE) -> bytes:
    library = b"legacy-forge-universal"
    profile = {
        "install": {
            "target": PROFILE_ID,
            "path": FORGE_COORDINATE,
            "filePath": f"/{FORGE_FILE}",
        },
        "versionInfo": {
            "id": PROFILE_ID,
            "inheritsFrom": "1.8.9",
            "mainClass": "net.minecraft.launchwrapper.Launch",
            "minecraftArguments": "--tweakClass net.minecraftforge.fml.common.launcher.FMLTweaker",
            "libraries": [
                {
                    "name": FORGE_COORDINATE,
                    "url": "http://files.minecraftforge.net/maven/",
                    "checksums": [hashlib.sha1(library, usedforsecurity=False).hexdigest()],
                }
            ],
        },
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("install_profile.json", json.dumps(profile))
        archive.writestr(embedded_name, library)
    return library


def test_supports_and_imports_legacy_installer(tmp_path: Path) -> None:
    installer = tmp_path / "forge-installer.jar"
    expected_library = create_legacy_installer(installer)
    staging = tmp_path / "staging"

    assert LegacyForgeInstaller.supports(installer) is True

    result = LegacyForgeInstaller.install(installer, staging)

    assert result.profile_id == PROFILE_ID
    assert result.profile["mainClass"] == "net.minecraft.launchwrapper.Launch"
    assert result.embedded_library.read_bytes() == expected_library
    assert result.embedded_library.relative_to(staging / "libraries").as_posix() == FORGE_PATH
    profile_path = staging / "versions" / PROFILE_ID / f"{PROFILE_ID}.json"
    assert json.loads(profile_path.read_text(encoding="utf-8"))["id"] == PROFILE_ID


def test_legacy_installer_finds_root_universal_when_file_path_is_nested(tmp_path: Path) -> None:
    installer = tmp_path / "forge-installer.jar"
    expected_library = create_legacy_installer(installer, embedded_name=f"/{FORGE_FILE}")

    result = LegacyForgeInstaller.install(installer, tmp_path / "staging")

    assert result.embedded_library.read_bytes() == expected_library


def test_rejects_legacy_installer_without_embedded_library(tmp_path: Path) -> None:
    installer = tmp_path / "forge-installer.jar"
    profile = {
        "install": {"target": PROFILE_ID, "path": FORGE_COORDINATE, "filePath": f"/{FORGE_FILE}"},
        "versionInfo": {"id": PROFILE_ID, "libraries": []},
    }
    with zipfile.ZipFile(installer, "w") as archive:
        archive.writestr("install_profile.json", json.dumps(profile))

    with pytest.raises(RuntimeError, match="does not contain the embedded library"):
        LegacyForgeInstaller.install(installer, tmp_path / "staging")


def test_rejects_unsafe_legacy_file_path() -> None:
    with pytest.raises(RuntimeError, match="Unsafe path"):
        LegacyForgeInstaller._safe_relative_path("../../outside.jar")


def test_maven_coordinate_supports_classifier_and_extension() -> None:
    result = LegacyForgeInstaller._maven_path("example.group:artifact:1.0:client@zip")

    assert result.as_posix() == "example/group/artifact/1.0/artifact-1.0-client.zip"
