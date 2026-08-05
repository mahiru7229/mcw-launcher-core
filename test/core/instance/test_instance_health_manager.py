from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_health_manager import InstanceHealthManager
from src.core.instance.instance_manager import InstanceManager
from src.models.instance.instance import Instance
from src.models.instance.instance_health import InstanceHealthState


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path):
    previous = Paths.configure(tmp_path)
    try:
        yield
    finally:
        Paths.restore(previous)


def _instance(name: str = "Healthy") -> Instance:
    directory = Paths.INSTANCES_ROOT / name
    directory.mkdir(parents=True, exist_ok=True)
    instance = Instance(instance_id="health-id", name=name, version_id="1.20.1", instance_dir=directory, mod_loader=("vanilla", "-1"))
    metadata = {
        "id": instance.instance_id,
        "name": instance.name,
        "version_id": instance.version_id,
        "mod_loader": list(instance.mod_loader),
        "metadata_version": InstanceManager.METADATA_VERSION,
        "icon": InstanceManager.DEFAULT_ICON,
    }
    (directory / "instance.json").write_text(json.dumps(metadata), encoding="utf-8")
    (directory / "settings.json").write_text("{}", encoding="utf-8")
    return instance


def test_fast_health_scan_reports_a_valid_instance_as_healthy() -> None:
    report = InstanceHealthManager.scan(_instance())

    assert report.state is InstanceHealthState.HEALTHY
    assert report.issues == ()


def test_invalid_metadata_is_corrupted() -> None:
    instance = _instance()
    (instance.instance_dir / "instance.json").write_text("{broken", encoding="utf-8")

    report = InstanceHealthManager.scan(instance)

    assert report.state is InstanceHealthState.CORRUPTED
    assert "metadata_invalid" in {issue.code for issue in report.issues}


def test_old_metadata_schema_requires_migration() -> None:
    instance = _instance()
    path = instance.instance_dir / "instance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metadata_version"] = InstanceManager.METADATA_VERSION - 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = InstanceHealthManager.scan(instance)

    assert report.state is InstanceHealthState.MIGRATION_REQUIRED
    assert report.repairable is True


def test_missing_configured_java_is_reported() -> None:
    instance = _instance()
    (instance.instance_dir / "settings.json").write_text(json.dumps({"java_path": str(Paths.root() / "missing-java.exe")}), encoding="utf-8")

    report = InstanceHealthManager.scan(instance)

    assert report.state is InstanceHealthState.MISSING_JAVA
    assert "configured_java_missing" in {issue.code for issue in report.issues}


def test_unfinished_operation_marks_instance_incomplete() -> None:
    instance = _instance()
    journal = Paths.instance_operations_root() / "unfinished.json"
    journal.write_text(
        json.dumps({
            "operation_id": "operation-id",
            "operation": "clone",
            "instance_name": instance.name,
            "phase": "committing",
            "target_path": str(instance.instance_dir),
        }),
        encoding="utf-8",
    )

    report = InstanceHealthManager.scan(instance)

    assert report.state is InstanceHealthState.INCOMPLETE
    assert "operation_incomplete" in {issue.code for issue in report.issues}


def test_missing_custom_icon_needs_attention() -> None:
    instance = _instance()
    instance.icon = ".mcw/instance-icon.png"

    report = InstanceHealthManager.scan(instance)

    assert report.state is InstanceHealthState.NEEDS_ATTENTION
    assert "icon_missing" in {issue.code for issue in report.issues}
