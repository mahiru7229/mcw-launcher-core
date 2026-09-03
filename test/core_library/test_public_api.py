from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

from mcw_core import CorePaths, InstanceHealthReport, InstanceHealthState, InstanceState, InstanceStatus, LaunchRequest, MCWCore, ProcessSession, ProcessSessionState
from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def restore_global_paths():
    snapshot = Paths.snapshot()
    try:
        yield
    finally:
        Paths.restore(snapshot)


def test_public_package_imports_without_pyside6() -> None:
    script = r'''
import importlib.abc
import sys

class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            raise ImportError("PySide6 is intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockQt())
import mcw_core
assert mcw_core.MCWCore
assert "PySide6" not in sys.modules
print(mcw_core.__version__)
'''
    completed = subprocess.run([sys.executable, "-c", script], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_core_paths_can_target_an_independent_root(tmp_path: Path) -> None:
    configured = CorePaths.from_root(tmp_path)
    configured.apply()

    assert Paths.root() == tmp_path.resolve()
    assert Paths.CACHE_ROOT == tmp_path / "cache"
    assert Paths.INSTANCES_ROOT == tmp_path / "instances"
    assert Paths.RUNTIMES_ROOT == tmp_path / "runtimes"
    assert Paths.INSTANCE_LOCKS_ROOT == tmp_path / "instances" / ".runtime" / "locks"
    assert Paths.INSTANCES_ROOT.is_dir()
    assert Paths.RUNTIMES_ROOT.is_dir()


def test_headless_facade_launches_an_offline_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mcw_core import facade

    instance = Instance(
        instance_id="headless-id",
        name="Headless Test",
        version_id="1.20.1",
        mod_loader=("quilt", "0.30.1"),
        instance_dir=tmp_path / "instances" / "Headless Test",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(facade.InstanceManager, "load", lambda name: instance)

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "javaPath": tmp_path / "runtimes" / "java-17" / "bin" / "javaw.exe",
            "minecraftJavaMajorVersion": 17,
            "minecraftVersion": "quilt-loader-0.30.1-1.20.1",
            "warnings": ("headless smoke warning",),
        }

    monkeypatch.setattr(facade.MinecraftExecutor, "run", fake_run)
    core = MCWCore(CorePaths.from_root(tmp_path))
    confirmation_callback = lambda request: True
    result = core.launch(
        LaunchRequest(
            instance="Headless Test",
            offline_username="LibraryPlayer",
            on_compatibility_confirmation=confirmation_callback,
        )
    )

    assert captured["instance"] is instance
    assert captured["account"].username == "LibraryPlayer"
    assert captured["authentication"].player_name == "LibraryPlayer"
    assert captured["on_compatibility_confirmation"] is confirmation_callback
    assert result.minecraft_java_major_version == 17
    assert result.minecraft_version == "quilt-loader-0.30.1-1.20.1"
    assert result["warnings"] == ("headless smoke warning",)



def test_optifine_service_is_available_from_public_facade(tmp_path: Path) -> None:
    core = MCWCore(CorePaths.from_root(tmp_path))
    assert core.optifine.OFFICIAL_DOWNLOADS_URL == "https://optifine.net/downloads"


def test_platform_storage_migration_is_available_from_public_api() -> None:
    from mcw_core.api.storage import PlatformStorageMigration, PlatformStorageMigrationReport

    assert PlatformStorageMigration.MARKER_NAME == ".platform-storage-migration-v1.json"
    assert PlatformStorageMigrationReport().completed is True


def test_instance_state_types_are_public() -> None:
    assert InstanceState.RUNNING.value == "running"
    status = InstanceStatus(instance_id="id", name="Example", state=InstanceState.READY)
    assert status.state is InstanceState.READY


def test_stability_types_are_public(tmp_path: Path) -> None:
    report = InstanceHealthReport(instance_id="id", name="Example", state=InstanceHealthState.HEALTHY, issues=(), checked_at="now")
    session = ProcessSession(
        session_id="session",
        instance_id="id",
        instance_name="Example",
        instance_dir=tmp_path,
        state=ProcessSessionState.RUNNING,
        launcher_pid=1,
        root_pid=2,
        child_pids=(),
        started_at="now",
        updated_at="now",
    )

    assert report.healthy is True
    assert session.active is True

def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def test_core_has_no_gui_or_qt_dependency() -> None:
    violations: list[str] = []
    for root in (PROJECT_ROOT / "src" / "core", PROJECT_ROOT / "src" / "models"):
        for path in root.rglob("*.py"):
            for module in _imports(path):
                if module == "src.gui" or module.startswith("src.gui.") or module in {"PySide6", "PyQt6", "PyQt5"} or module.startswith(("PySide6.", "PyQt6.", "PyQt5.")):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not violations, "Core dependency violations:\n" + "\n".join(violations)


def test_headless_distribution_excludes_gui_and_pyside_dependency() -> None:
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = tuple(data["project"]["dependencies"])
    package_find = data["tool"]["setuptools"]["packages"]["find"]

    assert all("pyside" not in item.casefold() for item in dependencies)
    assert "src.gui*" in package_find["exclude"]
    assert "mcw_core*" in package_find["include"]


def test_packaged_lan_agent_is_available_outside_project_root(tmp_path: Path) -> None:
    from src.core.lan.lan_agent_manager import LanAgentManager

    CorePaths.from_root(tmp_path).apply()
    bundled = LanAgentManager._bundled_agent_path()

    assert bundled.name == LanAgentManager.AGENT_FILENAME
    assert bundled.is_file()
    assert LanAgentManager._sha256(bundled) == LanAgentManager.AGENT_SHA256


def test_instance_service_exposes_library_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mcw_core.services import InstanceService

    expected = Instance("id", "Organized", "1.20.1", tmp_path / "instances" / "Organized", ("forge", "47.4.0"), favorite=True, group="Modpacks", tags=("heavy",))
    captured: dict[str, object] = {}

    def fake_update(name: str, **changes):
        captured["name"] = name
        captured.update(changes)
        return expected

    monkeypatch.setattr("mcw_core.services.InstanceManager.set_library_metadata", fake_update)

    result = InstanceService.set_library_metadata("Organized", favorite=True, group="Modpacks", tags=["heavy"])

    assert result is expected
    assert captured == {"name": "Organized", "favorite": True, "group": "Modpacks", "tags": ["heavy"]}
