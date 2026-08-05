import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.instance.errors import InstanceAlreadyRunningError
from src.core.instance.instance_run_lock import InstanceRunLock


@pytest.fixture(autouse=True)
def isolate_lock_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(Paths, "INSTANCE_LOCKS_ROOT", tmp_path / ".runtime" / "locks")


def make_instance(tmp_path: Path, name: str = "Test Instance"):
    instance_dir = tmp_path / name
    instance_dir.mkdir(parents=True)
    return SimpleNamespace(instance_id=f"instance-{name}", name=name, instance_dir=instance_dir)


class ControlledProcess:
    def __init__(self, pid: int = 43210) -> None:
        self.pid = pid
        self.wait_started = threading.Event()
        self.exit_requested = threading.Event()

    def wait(self) -> int:
        self.wait_started.set()
        self.exit_requested.wait(timeout=2)
        return 0


def wait_until_missing(path: Path, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout

    while path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert not path.exists()


def test_acquire_creates_preparing_lock(tmp_path: Path):
    instance = make_instance(tmp_path)

    run_lock = InstanceRunLock.acquire(instance)
    payload = json.loads(run_lock.lock_path.read_text(encoding="utf-8"))

    assert payload["instance_id"] == "instance-Test Instance"
    assert payload["instance_name"] == "Test Instance"
    assert payload["state"] == "preparing"
    assert payload["launcher_pid"] == os.getpid()
    assert payload["minecraft_pid"] is None
    assert run_lock.lock_path.parent == Paths.INSTANCE_LOCKS_ROOT
    assert not (instance.instance_dir / InstanceRunLock.LOCK_FILENAME).exists()

    run_lock.release()


def test_second_acquire_is_blocked_while_same_instance_is_preparing(tmp_path: Path):
    instance = make_instance(tmp_path)
    run_lock = InstanceRunLock.acquire(instance)

    with pytest.raises(InstanceAlreadyRunningError, match="Test Instance"):
        InstanceRunLock.acquire(instance)

    run_lock.release()


def test_different_instances_can_be_locked_at_the_same_time(tmp_path: Path):
    first = make_instance(tmp_path, "First")
    second = make_instance(tmp_path, "Second")

    first_lock = InstanceRunLock.acquire(first)
    second_lock = InstanceRunLock.acquire(second)

    assert first_lock.lock_path.exists()
    assert second_lock.lock_path.exists()

    first_lock.release()
    second_lock.release()


def test_track_process_keeps_lock_until_process_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance = make_instance(tmp_path)
    process = ControlledProcess()
    run_lock = InstanceRunLock.acquire(instance)

    monkeypatch.setattr(InstanceRunLock, "_is_process_alive", staticmethod(lambda pid: pid in {os.getpid(), process.pid}))

    assert run_lock.track_process(process) is True
    assert process.wait_started.wait(timeout=1)

    payload = json.loads(run_lock.lock_path.read_text(encoding="utf-8"))
    assert payload["state"] == "running"
    assert payload["minecraft_pid"] == process.pid

    with pytest.raises(InstanceAlreadyRunningError):
        InstanceRunLock.acquire(instance)

    process.exit_requested.set()
    wait_until_missing(run_lock.lock_path)


def test_stale_lock_is_replaced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance = make_instance(tmp_path)
    lock_path = InstanceRunLock.lock_path_for(instance)
    lock_path.write_text(json.dumps({"token": "stale", "state": "running", "launcher_pid": 100, "minecraft_pid": 200}), encoding="utf-8")

    monkeypatch.setattr(InstanceRunLock, "_is_process_alive", staticmethod(lambda pid: False))

    run_lock = InstanceRunLock.acquire(instance)
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    assert payload["token"] == run_lock.token
    assert payload["token"] != "stale"

    run_lock.release()


def test_release_does_not_remove_lock_owned_by_another_token(tmp_path: Path):
    instance = make_instance(tmp_path)
    run_lock = InstanceRunLock.acquire(instance)
    replacement = json.loads(run_lock.lock_path.read_text(encoding="utf-8"))
    replacement["token"] = "another-owner"
    InstanceRunLock._replace_lock_file(run_lock.lock_path, replacement)

    run_lock.release()

    assert run_lock.lock_path.exists()
    run_lock.lock_path.unlink()


def test_invalid_process_releases_lock_instead_of_leaving_instance_stuck(tmp_path: Path):
    instance = make_instance(tmp_path)
    run_lock = InstanceRunLock.acquire(instance)

    assert run_lock.track_process(object()) is False
    assert not run_lock.lock_path.exists()


def test_concurrent_acquire_allows_only_one_owner(tmp_path: Path):
    instance = make_instance(tmp_path)
    barrier = threading.Barrier(2)

    def acquire():
        barrier.wait(timeout=1)
        try:
            return InstanceRunLock.acquire(instance)
        except InstanceAlreadyRunningError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: acquire(), range(2)))

    acquired = [result for result in results if result is not None]

    assert len(acquired) == 1
    acquired[0].release()


def test_preparing_lock_can_authorize_managed_content_changes(tmp_path: Path):
    instance = make_instance(tmp_path)
    run_lock = InstanceRunLock.acquire(instance)

    assert InstanceRunLock.owns_preparing_lock(instance, run_lock.token) is True
    assert InstanceRunLock.owns_preparing_lock(instance, "wrong-token") is False
    assert InstanceRunLock.owns_preparing_lock(instance, None) is False

    run_lock.release()


def test_running_lock_cannot_authorize_mod_changes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance = make_instance(tmp_path)
    process = ControlledProcess()
    run_lock = InstanceRunLock.acquire(instance)
    monkeypatch.setattr(InstanceRunLock, "_is_process_alive", staticmethod(lambda pid: pid in {os.getpid(), process.pid}))

    assert run_lock.track_process(process) is True
    assert process.wait_started.wait(timeout=1)
    assert InstanceRunLock.owns_preparing_lock(instance, run_lock.token) is False

    process.exit_requested.set()
    wait_until_missing(run_lock.lock_path)


def test_reconcile_removes_stale_lock_and_reports_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance = make_instance(tmp_path, "Stale Instance")
    lock_path = InstanceRunLock.lock_path_for(instance)
    lock_path.write_text(json.dumps({"instance_name": instance.name, "state": "running", "launcher_pid": 111, "minecraft_pid": 222}), encoding="utf-8")
    monkeypatch.setattr(InstanceRunLock, "_is_process_alive", staticmethod(lambda _pid: False))

    assert InstanceRunLock.reconcile() == ("Stale Instance",)
    assert not lock_path.exists()
