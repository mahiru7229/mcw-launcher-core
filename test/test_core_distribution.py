from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib
import zipfile

import mcw_core
from src.config import CURSEFORGE_DEFAULT_GATEWAY_URL, UPDATE_CHANNEL, VERSION_ID


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_distribution_and_runtime_versions_match() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "mcw-core"
    assert project["version"] == "1.5.0"
    assert VERSION_ID == project["version"]
    assert mcw_core.__version__ == project["version"]
    assert UPDATE_CHANNEL == "stable"


def test_installed_distribution_version_matches_source() -> None:
    try:
        installed = version("mcw-core")
    except PackageNotFoundError:
        return
    assert installed == "1.5.0"


def test_source_distribution_excludes_launcher_gui() -> None:
    assert not (PROJECT_ROOT / "src" / "gui").exists()
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert all("pyside" not in dependency.casefold() for dependency in project["project"]["dependencies"])


def test_gateway_source_is_present_without_bundled_credentials() -> None:
    gateway = PROJECT_ROOT / "mcw-curseforge-gateway-main.zip"
    assert gateway.is_file()
    assert CURSEFORGE_DEFAULT_GATEWAY_URL == ""
    with zipfile.ZipFile(gateway) as archive:
        names = {name.replace("\\", "/") for name in archive.namelist()}
        assert any(name.endswith("/vercel.json") for name in names)
        assert any(name.endswith("/api/health.js") for name in names)
        assert not any(name.endswith("/.env.local") for name in names)
        assert not any("node_modules/" in name for name in names)
