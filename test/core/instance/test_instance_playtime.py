from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.models.instance.instance import Instance


@pytest.fixture
def temporary_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    instances_root = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances_root)
    return instances_root


def test_instance_playtime_persistence(temporary_paths: Path) -> None:
    instance_dir = temporary_paths / "PlaytimeTest"
    instance = Instance(
        instance_id="test-playtime-uuid",
        name="PlaytimeTest",
        version_id="1.20.1",
        instance_dir=instance_dir,
        mod_loader=("vanilla", "-1"),
        total_playtime_seconds=3600,
        last_played="2026-09-13T10:00:00+00:00",
    )
    instance_dir.mkdir(parents=True, exist_ok=True)
    InstanceManager._save_instance_metadata(instance)

    # Verify JSON file has total_play_time_seconds
    data = json.loads((instance_dir / "instance.json").read_text(encoding="utf-8"))
    assert data.get("total_play_time_seconds") == 3600
    assert data.get("last_played") == "2026-09-13T10:00:00+00:00"

    # Verify reload
    reloaded_instance = InstanceManager.load("PlaytimeTest")
    assert reloaded_instance.total_playtime_seconds == 3600
    assert reloaded_instance.last_played == "2026-09-13T10:00:00+00:00"
