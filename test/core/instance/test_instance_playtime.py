from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.gui.formatters.time_formatter import format_last_played, format_playtime
from src.models.instance.instance import Instance


@pytest.fixture
def temporary_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    instances_root = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances_root)
    return instances_root


def test_format_playtime() -> None:
    assert format_playtime(0) in {"Chưa từng chơi", "Never played"}
    assert format_playtime(40) in {"Dưới 1 phút", "< 1 minute"}
    assert "2" in format_playtime(120)
    assert "1" in format_playtime(3600)
    formatted = format_playtime(5400)
    assert "1" in formatted and "30" in formatted


def test_format_last_played() -> None:
    assert format_last_played("") in {"Chưa từng chơi", "Never"}
    assert format_last_played(None) in {"Chưa từng chơi", "Never"}

    now = datetime.now(timezone.utc)
    today_str = now.isoformat()
    today_result = format_last_played(today_str)
    assert "Hôm nay" in today_result or "Today" in today_result

    yesterday_str = (now - timedelta(days=1)).isoformat()
    yesterday_result = format_last_played(yesterday_str)
    assert "Hôm qua" in yesterday_result or "Yesterday" in yesterday_result

    five_days_str = (now - timedelta(days=5)).isoformat()
    five_days_result = format_last_played(five_days_str)
    assert "5" in five_days_result


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
