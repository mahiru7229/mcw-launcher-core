from pathlib import Path

import pytest

from src.core.update.update_cleanup import UpdateCleanupRequest, UpdateCleanupWorker, consume_update_cleanup_arguments


def test_consumes_cleanup_arguments_and_preserves_launcher_arguments(tmp_path, monkeypatch) -> None:
    temporary_root = tmp_path / "temp"
    updater_directory = temporary_root / "mcw-launcher-updater-test"
    updater_directory.mkdir(parents=True)
    monkeypatch.setattr("src.core.update.update_cleanup.tempfile.gettempdir", lambda: str(temporary_root))

    cleaned, request = consume_update_cleanup_arguments([
        "MCW Launcher.exe",
        "--cleanup-update",
        str(updater_directory),
        "1234",
        "--other-option",
    ])

    assert cleaned == ["MCW Launcher.exe", "--other-option"]
    assert request == UpdateCleanupRequest(updater_directory=updater_directory, updater_pid=1234)


def test_rejects_cleanup_directory_outside_system_temp(tmp_path, monkeypatch) -> None:
    temporary_root = tmp_path / "temp"
    temporary_root.mkdir()
    unsafe_directory = tmp_path / "mcw-launcher-updater-unsafe"
    unsafe_directory.mkdir()
    monkeypatch.setattr("src.core.update.update_cleanup.tempfile.gettempdir", lambda: str(temporary_root))

    with pytest.raises(RuntimeError, match="system temporary directory"):
        consume_update_cleanup_arguments(["MCW Launcher.exe", "--cleanup-update", str(unsafe_directory), "1234"])


def test_cleanup_worker_waits_then_removes_updater_directory(tmp_path, monkeypatch) -> None:
    temporary_root = tmp_path / "temp"
    updater_directory = temporary_root / "mcw-launcher-updater-test"
    updater_directory.mkdir(parents=True)
    (updater_directory / "MCW Launcher Updater.exe").write_bytes(b"updater")
    monkeypatch.setattr("src.core.update.update_cleanup.tempfile.gettempdir", lambda: str(temporary_root))

    worker = UpdateCleanupWorker(UpdateCleanupRequest(updater_directory=updater_directory, updater_pid=1234))
    waits: list[int] = []
    monkeypatch.setattr(worker, "_wait_for_process_exit", lambda pid: waits.append(pid))

    worker.run()

    assert waits == [1234]
    assert not updater_directory.exists()
