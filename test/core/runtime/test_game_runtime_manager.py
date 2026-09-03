import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.java.java_runtime import JavaRuntime
from src.core.runtime.game_runtime_manager import GameRuntimeManager
from src.core.runtime.process_supervisor import ProcessSupervisor


class FinishedProcess:
    def __init__(self, exit_code: int, pid: int = 43210) -> None:
        self.pid = pid
        self.returncode = exit_code

    def poll(self) -> int:
        return self.returncode


@pytest.fixture
def instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    instance_dir = tmp_path / "instances" / "Runtime Test"
    instance_dir.mkdir(parents=True)
    metadata = {
        "id": "runtime-test",
        "name": "Runtime Test",
        "version_id": "1.21.1",
        "mod_loader": ["vanilla", "-1"],
        "instance_dir": str(instance_dir),
        "notes": "keep this field",
    }
    (instance_dir / "instance.json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(Paths, "load_instance_dir", lambda name: instance_dir)
    return SimpleNamespace(name="Runtime Test", instance_dir=instance_dir)


def test_watch_process_records_normal_exit(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    started_at = datetime.now(timezone.utc) - timedelta(seconds=65)
    log_path = Path(instance.instance_dir) / "logs" / "minecraft-test.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("game output", encoding="utf-8")
    closed = []
    results = []

    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: log_path))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: closed.append(process.pid)))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", started_at, results.append)

    assert len(results) == 1
    result = results[0]
    assert result.exit_code == 0
    assert result.crashed is False
    assert result.duration_seconds >= 60
    assert result.log_path == log_path
    assert closed == [43210]

    history = json.loads(Paths.instance_runtime_history(instance).read_text(encoding="utf-8"))
    assert history["records"][-1]["exit_code"] == 0

    metadata = json.loads(Paths.instance_metadata(instance.name).read_text(encoding="utf-8"))
    assert metadata["notes"] == "keep this field"
    assert metadata["last_launch_crashed"] is False
    assert metadata["total_play_time_seconds"] >= 60


def test_new_crash_report_marks_zero_exit_as_crash(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    crash_dir = Paths.instance_crash_reports_dir(instance)
    crash_report = crash_dir / "crash-2026-07-15.txt"
    crash_report.write_text("crash", encoding="utf-8")
    results = []

    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", started_at, results.append)

    assert results[0].crashed is True
    assert results[0].crash_report_path == crash_report


def test_nonzero_exit_is_crash_without_report(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    results = []
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))

    GameRuntimeManager._watch_process(FinishedProcess(1), instance, "1.21.1", datetime.now(timezone.utc), results.append)

    assert results[0].crashed is True
    assert results[0].exit_code == 1
    assert results[0].crash_report_path is None


def test_watch_rejects_object_without_poll(instance) -> None:
    assert GameRuntimeManager.watch(object(), instance, "1.21.1", datetime.now(timezone.utc)) is False


def test_callback_still_runs_when_runtime_history_cannot_be_written(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    results = []
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(GameRuntimeManager, "_append_history", classmethod(lambda cls, received_instance, result: (_ for _ in ()).throw(OSError("disk full"))))
    monkeypatch.setattr(GameRuntimeManager, "_update_instance_metadata", classmethod(lambda cls, received_instance, result: None))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", datetime.now(timezone.utc), results.append)

    assert len(results) == 1
    assert results[0].exit_code == 0


class StoppableProcess:
    def __init__(self) -> None:
        self.pid = 54321
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def test_stop_terminates_registered_instance_process(instance) -> None:
    process = StoppableProcess()
    GameRuntimeManager._active_processes.clear()
    GameRuntimeManager._register_process(instance, process)

    assert GameRuntimeManager.stop(instance, graceful_timeout=0.1) is True
    assert process.terminated is True
    assert process.killed is False
    assert GameRuntimeManager._active_process(instance) is None


def test_process_session_finishes_even_when_runtime_history_write_fails(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    finished: list[tuple[str, int, bool]] = []
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(GameRuntimeManager, "_record_result", classmethod(lambda cls, received_instance, result: (_ for _ in ()).throw(OSError("disk full"))))
    monkeypatch.setattr(ProcessSupervisor, "finish", classmethod(lambda cls, session_id, exit_code, crashed, detail="": finished.append((session_id, exit_code, crashed))))

    with pytest.raises(OSError, match="disk full"):
        GameRuntimeManager._watch_process(FinishedProcess(1), instance, "1.21.1", datetime.now(timezone.utc), None, "session-id")

    assert finished == [("session-id", 1, True)]


def test_old_crash_report_is_ignored_for_new_session(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    crash_dir = Paths.instance_crash_reports_dir(instance)
    old_report = crash_dir / "crash-old.txt"
    old_report.write_text("old crash", encoding="utf-8")
    snapshot = GameRuntimeManager.crash_report_snapshot(instance)
    results = []

    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(ProcessSupervisor, "stop_requested", classmethod(lambda cls, session_id: False))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", datetime.now(timezone.utc), results.append, "new-session", snapshot)

    assert results[0].crashed is False
    assert results[0].crash_report_path is None


def test_new_crash_report_after_snapshot_is_detected(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    crash_dir = Paths.instance_crash_reports_dir(instance)
    old_report = crash_dir / "crash-old.txt"
    old_report.write_text("old crash", encoding="utf-8")
    snapshot = GameRuntimeManager.crash_report_snapshot(instance)
    new_report = crash_dir / "crash-new.txt"
    new_report.write_text("new crash", encoding="utf-8")
    results = []

    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(ProcessSupervisor, "stop_requested", classmethod(lambda cls, session_id: False))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", datetime.now(timezone.utc), results.append, "new-session", snapshot)

    assert results[0].crashed is True
    assert results[0].crash_report_path == new_report


def test_successful_second_session_replaces_previous_crash_state(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    metadata_path = Paths.instance_metadata(instance.name)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({
        "last_launch_crashed": True,
        "last_launch_state": "crashed",
        "last_session_id": "first-session",
        "last_started_at": "2026-08-02T00:00:00+00:00",
    })
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    started_at = datetime.now(timezone.utc)
    GameRuntimeManager.record_start(instance, started_at, "second-session")
    snapshot = GameRuntimeManager.crash_report_snapshot(instance)

    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(ProcessSupervisor, "stop_requested", classmethod(lambda cls, session_id: False))

    GameRuntimeManager._watch_process(FinishedProcess(0), instance, "1.21.1", started_at, None, "second-session", snapshot)

    updated = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert updated["last_session_id"] == "second-session"
    assert updated["last_launch_crashed"] is False
    assert updated["last_launch_state"] == "finished"
    assert updated["last_exit_code"] == 0


def test_stop_requested_is_not_classified_as_crash(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    results = []
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(ProcessSupervisor, "stop_requested", classmethod(lambda cls, session_id: True))

    GameRuntimeManager._watch_process(FinishedProcess(-9), instance, "1.21.1", datetime.now(timezone.utc), results.append, "stopped-session", {})

    assert results[0].stopped_by_launcher is True
    assert results[0].crashed is False


def test_stale_session_cannot_overwrite_newer_runtime_result(instance) -> None:
    metadata_path = Paths.instance_metadata(instance.name)
    newer_started_at = datetime.now(timezone.utc)
    GameRuntimeManager.record_start(instance, newer_started_at, "newer-session")
    stale_result = __import__("src.models.runtime.game_exit_result", fromlist=["GameExitResult"]).GameExitResult(
        instance_name=instance.name,
        minecraft_version="1.21.1",
        pid=1,
        exit_code=1,
        started_at=(newer_started_at - timedelta(minutes=1)).isoformat(),
        ended_at=newer_started_at.isoformat(),
        duration_seconds=60,
        crashed=True,
        session_id="older-session",
    )

    GameRuntimeManager._update_instance_metadata(instance, stale_result)

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["last_session_id"] == "newer-session"
    assert "last_launch_state" not in metadata


def test_kill_force_kills_unsupervised_process(instance) -> None:
    process = StoppableProcess()
    GameRuntimeManager._active_processes.clear()
    GameRuntimeManager._register_process(instance, process)

    assert GameRuntimeManager.kill(instance, timeout=0.1) is True
    assert process.killed is True
    assert process.terminated is False
    assert GameRuntimeManager._active_process(instance) is None


def test_user_killed_session_is_not_classified_as_crash(monkeypatch: pytest.MonkeyPatch, instance) -> None:
    results = []
    monkeypatch.setattr(JavaRuntime, "log_path", classmethod(lambda cls, process: None))
    monkeypatch.setattr(JavaRuntime, "close_process_log", classmethod(lambda cls, process: None))
    monkeypatch.setattr(ProcessSupervisor, "kill_requested", classmethod(lambda cls, session_id: True))
    monkeypatch.setattr(ProcessSupervisor, "stop_requested", classmethod(lambda cls, session_id: True))

    GameRuntimeManager._watch_process(FinishedProcess(-9), instance, "1.21.1", datetime.now(timezone.utc), results.append, "killed-session", {})

    assert results[0].killed_by_user is True
    assert results[0].stopped_by_launcher is True
    assert results[0].crashed is False
