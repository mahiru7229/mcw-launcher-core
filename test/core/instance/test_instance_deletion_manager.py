from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.instance.errors import InstanceDeletionError
from src.core.instance.instance_deletion_manager import InstanceDeletionManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.runtime.game_runtime_manager import GameRuntimeManager


@pytest.fixture
def deletion_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", root)
    monkeypatch.setattr(Paths, "INSTANCE_LOCKS_ROOT", root / ".runtime" / "locks")
    monkeypatch.setattr(GameRuntimeManager, "stop", classmethod(lambda cls, instance, graceful_timeout=2.5: False))
    monkeypatch.setattr(InstanceRunLock, "active_for", classmethod(lambda cls, instance: None))
    monkeypatch.setattr(InstanceRunLock, "remove_for", classmethod(lambda cls, instance, force=False: True))
    monkeypatch.setattr(InstanceDeletionManager, "_find_relevant_processes", classmethod(lambda cls, target: ()))
    monkeypatch.setattr("src.core.instance.instance_deletion_manager.time.sleep", lambda _seconds: None)
    return root


def test_delete_retries_windows_locked_file_then_succeeds(deletion_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = InstanceManager.create("Locked Pack", SimpleNamespace(id="1.20.1"))
    locked = instance.instance_dir / "local" / "crash_assistant" / "helper.jar"
    locked.parent.mkdir(parents=True)
    locked.write_bytes(b"helper")
    real_rmtree = shutil.rmtree
    calls = []

    def flaky_rmtree(path: Path, *args, **kwargs) -> None:
        calls.append(Path(path))
        if len(calls) == 1:
            error = PermissionError(13, "file is in use", str(locked))
            error.winerror = 32
            raise error
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("src.core.instance.instance_deletion_manager.shutil.rmtree", flaky_rmtree)

    assert InstanceManager.delete_instance(instance.name) is True
    assert len(calls) == 2
    assert not instance.instance_dir.exists()
    assert not InstanceManager.is_instance_exist(instance.name)


def test_failed_delete_keeps_registry_and_queues_next_startup(deletion_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = InstanceManager.create("Still Locked", SimpleNamespace(id="1.20.1"))
    locked = instance.instance_dir / "local" / "crash_assistant" / "helper.jar"
    locked.parent.mkdir(parents=True)
    locked.write_bytes(b"helper")
    error = PermissionError(13, "file is in use", str(locked))
    error.winerror = 32
    monkeypatch.setattr(
        InstanceDeletionManager,
        "_delete_target",
        classmethod(lambda cls, target: (False, error, locked, ())),
    )

    with pytest.raises(InstanceDeletionError) as captured:
        InstanceManager.delete_instance(instance.name)

    assert captured.value.scheduled is True
    assert captured.value.locked_path == locked
    assert instance.instance_dir.exists()
    assert InstanceManager.is_instance_exist(instance.name)
    pending_path = deletion_paths / ".runtime" / "pending-instance-deletions.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending["entries"][0]["name"] == instance.name


def test_pending_delete_is_completed_before_instance_listing(deletion_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = InstanceManager.create("Pending Pack", SimpleNamespace(id="1.20.1"))
    InstanceDeletionManager.schedule(instance)

    def delete_target(target: Path):
        shutil.rmtree(target)
        return True, None, None, ()

    monkeypatch.setattr(InstanceDeletionManager, "_delete_target", classmethod(lambda cls, target: delete_target(target)))

    assert InstanceManager.list_instances() == []
    assert not instance.instance_dir.exists()
    assert not InstanceManager.is_instance_exist(instance.name)
    assert not (deletion_paths / ".runtime" / "pending-instance-deletions.json").exists()


def test_refuses_to_delete_path_outside_instance_root(deletion_paths: Path) -> None:
    outside = deletion_paths.parent / "outside"
    outside.mkdir()
    instance = SimpleNamespace(instance_id="outside", name="Outside", instance_dir=outside)

    with pytest.raises(RuntimeError, match="outside the configured instance root"):
        InstanceDeletionManager.delete(instance)
