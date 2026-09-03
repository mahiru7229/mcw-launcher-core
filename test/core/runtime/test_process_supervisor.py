from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.runtime.process_supervisor import ProcessSupervisor
from src.models.instance.instance import Instance
from src.models.runtime.process_session import ProcessSessionState


class FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.return_code: int | None = None
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = 0

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path):
    previous = Paths.configure(tmp_path)
    ProcessSupervisor._processes.clear()
    ProcessSupervisor._sessions_by_instance.clear()
    try:
        yield
    finally:
        ProcessSupervisor._processes.clear()
        ProcessSupervisor._sessions_by_instance.clear()
        Paths.restore(previous)


def _instance() -> Instance:
    path = Paths.INSTANCES_ROOT / "Core Test"
    path.mkdir(parents=True, exist_ok=True)
    return Instance(instance_id="core-test", name="Core Test", version_id="1.20.1", instance_dir=path, mod_loader=("vanilla", "-1"))


def test_begin_attach_and_finish_persist_a_session_history() -> None:
    instance = _instance()
    process = FakeProcess()

    started = ProcessSupervisor.begin(instance)
    attached = ProcessSupervisor.attach(started.session_id, process)

    assert attached.state is ProcessSessionState.RUNNING
    assert attached.root_pid == process.pid
    assert ProcessSupervisor.active_for(instance).session_id == started.session_id

    finished = ProcessSupervisor.finish(started.session_id, exit_code=0, crashed=False)

    assert finished is not None
    assert finished.state is ProcessSessionState.FINISHED
    assert not (Paths.process_sessions_root() / f"{started.session_id}.json").exists()
    history = Paths.process_session_history_root() / f"{started.session_id}.json"
    assert json.loads(history.read_text(encoding="utf-8"))["state"] == "finished"
    assert ProcessSupervisor.active_for(instance) is None


def test_stop_instance_uses_only_the_registered_process_object() -> None:
    instance = _instance()
    process = FakeProcess()
    session = ProcessSupervisor.begin(instance)
    ProcessSupervisor.attach(session.session_id, process)

    stopped = ProcessSupervisor.stop_instance(instance, graceful_timeout=0.01)

    assert stopped is True
    assert process.terminated is True
    assert process.killed is False


def test_reconcile_archives_a_stale_session(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _instance()
    session = ProcessSupervisor.begin(instance)
    monkeypatch.setattr(ProcessSupervisor, "_pid_alive", staticmethod(lambda _pid: False))

    interrupted = ProcessSupervisor.reconcile()

    assert interrupted == ("Core Test",)
    history = Paths.process_session_history_root() / f"{session.session_id}.json"
    assert json.loads(history.read_text(encoding="utf-8"))["state"] == "interrupted"
    assert not (Paths.process_sessions_root() / f"{session.session_id}.json").exists()


def test_atomic_session_write_removes_temporary_file_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _instance()
    monkeypatch.setattr("src.core.runtime.process_supervisor.os.fsync", lambda _fd: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        ProcessSupervisor.begin(instance)

    root = Paths.process_sessions_root()
    assert tuple(root.glob("*.json")) == ()
    assert tuple(root.glob("*.tmp")) == ()


def test_stop_instance_terminates_verified_root_and_registered_children(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _instance()
    process = FakeProcess(pid=5000)
    session = ProcessSupervisor.begin(instance)
    ProcessSupervisor.attach(session.session_id, process)
    ProcessSupervisor.register_child(session.session_id, 5001)
    ProcessSupervisor._processes.clear()
    alive = {5000, 5001}
    terminated: list[tuple[int, bool]] = []

    monkeypatch.setattr(ProcessSupervisor, "_pid_alive", staticmethod(lambda pid: pid in alive))
    monkeypatch.setattr(ProcessSupervisor, "_pid_matches_instance", classmethod(lambda cls, pid, instance_dir: pid in alive))

    def terminate(pid: int, force: bool) -> None:
        terminated.append((pid, force))
        alive.discard(pid)

    monkeypatch.setattr(ProcessSupervisor, "_terminate_pid_tree", staticmethod(terminate))

    assert ProcessSupervisor.stop_instance(instance, graceful_timeout=0.01) is True
    assert {pid for pid, _force in terminated} == {5000, 5001}
    assert not (Paths.process_sessions_root() / f"{session.session_id}.json").exists()


def test_kill_instance_force_kills_registered_process_and_marks_session() -> None:
    instance = _instance()
    process = FakeProcess()
    session = ProcessSupervisor.begin(instance)
    ProcessSupervisor.attach(session.session_id, process)

    assert ProcessSupervisor.kill_instance(instance, timeout=0.01) is True
    assert process.killed is True
    assert process.terminated is False
    current = ProcessSupervisor.active_for(instance)
    assert current is not None
    assert current.state is ProcessSessionState.KILLING
    assert current.detail == "killed_by_user"
    assert ProcessSupervisor.kill_requested(session.session_id) is True


def test_posix_termination_targets_dedicated_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr("src.core.runtime.process_supervisor.PlatformInfo.is_windows", lambda: False)
    monkeypatch.setattr(
        "src.core.runtime.process_supervisor.signal",
        SimpleNamespace(SIGTERM=15, SIGKILL=9),
    )
    monkeypatch.setattr(
        "src.core.runtime.process_supervisor.os",
        SimpleNamespace(
            getpid=lambda: 100,
            getpgid=lambda pid: pid,
            getpgrp=lambda: 100,
            killpg=lambda pid, sig: calls.append((pid, sig)),
            kill=lambda _pid, _sig: (_ for _ in ()).throw(AssertionError("group signal expected")),
        ),
    )

    ProcessSupervisor._terminate_pid_tree(4321, force=False)

    assert calls == [(4321, 15)]


def test_posix_termination_falls_back_to_root_pid_without_owned_group(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr("src.core.runtime.process_supervisor.PlatformInfo.is_windows", lambda: False)
    monkeypatch.setattr(
        "src.core.runtime.process_supervisor.signal",
        SimpleNamespace(SIGTERM=15, SIGKILL=9),
    )
    monkeypatch.setattr(
        "src.core.runtime.process_supervisor.os",
        SimpleNamespace(
            getpid=lambda: 100,
            getpgid=lambda _pid: 200,
            getpgrp=lambda: 200,
            kill=lambda pid, sig: calls.append((pid, sig)),
        ),
    )

    ProcessSupervisor._terminate_pid_tree(4321, force=True)

    assert calls == [(4321, 9)]
