from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

import mcw_core
from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL, UPDATE_CHANNEL, VERSION_ID


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_and_runtime_versions_match() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "mcw-core"
    assert project["version"] == "1.5.1"
    assert VERSION_ID == project["version"]
    assert mcw_core.__version__ == project["version"]
    assert UPDATE_CHANNEL == "stable"


def test_installed_distribution_version_matches_source() -> None:
    try:
        installed = version("mcw-core")
    except PackageNotFoundError:
        return
    assert installed == "1.5.1"


def test_source_distribution_excludes_launcher_gui() -> None:
    assert not (PROJECT_ROOT / "src" / "gui").exists()
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert all("pyside" not in dependency.casefold() for dependency in project["project"]["dependencies"])


def test_gateway_source_archive_is_not_bundled() -> None:
    gateway = PROJECT_ROOT / "mcw-curseforge-gateway-main.zip"
    assert not gateway.exists()
    assert CURSEFORGE_DEFAULT_GATEWAY_URL == ""
