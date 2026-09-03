from pathlib import Path
import os

import pytest

from src.core.update.update_applier import UpdateApplier, UpdateApplyRequest


def make_request(tmp_path: Path) -> UpdateApplyRequest:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    updater = tmp_path / "updater"
    staging = tmp_path / "staging"
    source.mkdir()
    destination.mkdir()
    updater.mkdir()
    staging.mkdir()
    return UpdateApplyRequest(
        parent_pid=123,
        source_directory=source,
        destination_directory=destination,
        executable_name="MCW Launcher.exe",
        updater_directory=updater,
        staging_directory=staging,
        persistent_log_path=destination / "logs" / "updater.log",
        target_version="0.5.0-beta.3",
    )


def test_update_applier_replaces_files_and_restarts(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    (request.source_directory / "MCW Launcher.exe").write_bytes(b"new-exe")
    (request.source_directory / "lang").mkdir()
    (request.source_directory / "lang" / "en-US.json").write_text("new-language", encoding="utf-8")
    (request.destination_directory / "MCW Launcher.exe").write_bytes(b"old-exe")

    applier = UpdateApplier(request)
    starts: list[bool] = []
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda: starts.append(True))

    assert applier.run() == 0
    assert (request.destination_directory / "MCW Launcher.exe").read_bytes() == b"new-exe"
    assert (request.destination_directory / "lang" / "en-US.json").read_text(encoding="utf-8") == "new-language"
    assert starts == [True]
    assert not request.staging_directory.exists()
    assert "Update to 0.5.0-beta.3 completed" in request.persistent_log_path.read_text(encoding="utf-8")


def test_update_applier_rolls_back_and_restarts_previous_launcher(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source_exe = request.source_directory / "MCW Launcher.exe"
    destination_exe = request.destination_directory / "MCW Launcher.exe"
    source_exe.write_bytes(b"new-exe")
    destination_exe.write_bytes(b"old-exe")

    applier = UpdateApplier(request)
    starts: list[bool] = []
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_show_error", lambda _message: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda: starts.append(True))

    def fail_after_partial_copy() -> None:
        destination_exe.write_bytes(b"partial")
        raise RuntimeError("simulated copy failure")

    monkeypatch.setattr(applier, "_copy_update_files", fail_after_partial_copy)

    assert applier.run() == 1
    assert destination_exe.read_bytes() == b"old-exe"
    assert starts == [True]
    log = request.persistent_log_path.read_text(encoding="utf-8")
    assert "Update failed: simulated copy failure" in log
    assert "Rollback completed" in log


def test_update_request_loads_and_validates_json(tmp_path) -> None:
    request = make_request(tmp_path)
    (request.source_directory / "MCW Launcher.exe").write_bytes(b"exe")
    request_path = request.updater_directory / "request.json"
    request_path.write_text(
        """{
  "schema_version": 1,
  "parent_pid": 123,
  "source_directory": "%s",
  "destination_directory": "%s",
  "executable_name": "MCW Launcher.exe",
  "updater_directory": "%s",
  "staging_directory": "%s",
  "persistent_log_path": "%s",
  "target_version": "0.5.0-beta.3"
}""" % (
            str(request.source_directory).replace("\\", "\\\\"),
            str(request.destination_directory).replace("\\", "\\\\"),
            str(request.updater_directory).replace("\\", "\\\\"),
            str(request.staging_directory).replace("\\", "\\\\"),
            str(request.persistent_log_path).replace("\\", "\\\\"),
        ),
        encoding="utf-8",
    )

    loaded = UpdateApplyRequest.load(request_path)
    assert loaded.target_version == "0.5.0-beta.3"
    assert loaded.executable_name == "MCW Launcher.exe"


def test_start_launcher_passes_hidden_cleanup_request(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    executable = request.destination_directory / request.executable_name
    executable.write_bytes(b"exe")
    applier = UpdateApplier(request)
    calls: list[tuple[list[str], dict]] = []

    class FakeProcess:
        pass

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr("src.core.update.update_applier.subprocess.Popen", fake_popen)
    monkeypatch.setattr("src.core.update.update_applier.os.getpid", lambda: 9876)

    applier._start_launcher()

    assert calls[0][0] == [str(executable), "--cleanup-update", str(request.updater_directory), "9876"]
    assert calls[0][1]["stdout"] is not None
    assert calls[0][1]["stderr"] is not None


def write_update_manifest(root: Path, files: list[str], version: str) -> None:
    import json

    (root / "mcw-update.json").write_text(
        json.dumps({
            "schema_version": 1,
            "version": version,
            "platform": "windows-x64",
            "executable": "MCW Launcher.exe",
            "files": files,
        }),
        encoding="utf-8",
    )


def test_update_applier_removes_files_managed_by_previous_release(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    (request.source_directory / "MCW Launcher.exe").write_bytes(b"new-exe")
    (request.destination_directory / "MCW Launcher.exe").write_bytes(b"old-exe")
    stale = request.destination_directory / "docs" / "obsolete.md"
    stale.parent.mkdir()
    stale.write_text("obsolete", encoding="utf-8")
    write_update_manifest(request.destination_directory, ["MCW Launcher.exe", "docs/obsolete.md", "mcw-update.json"], "1.3.1")
    write_update_manifest(request.source_directory, ["MCW Launcher.exe", "mcw-update.json"], "1.3.2")

    applier = UpdateApplier(request)
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda: None)

    assert applier.run() == 0
    assert not stale.exists()


def test_update_applier_restores_removed_managed_file_on_rollback(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    (request.source_directory / "MCW Launcher.exe").write_bytes(b"new-exe")
    (request.destination_directory / "MCW Launcher.exe").write_bytes(b"old-exe")
    stale = request.destination_directory / "docs" / "obsolete.md"
    stale.parent.mkdir()
    stale.write_text("obsolete", encoding="utf-8")
    write_update_manifest(request.destination_directory, ["MCW Launcher.exe", "docs/obsolete.md", "mcw-update.json"], "1.3.1")
    write_update_manifest(request.source_directory, ["MCW Launcher.exe", "mcw-update.json"], "1.3.2")

    applier = UpdateApplier(request)
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda: None)
    monkeypatch.setattr(applier, "_show_error", lambda _message: None)
    monkeypatch.setattr(applier, "_verify_updated_executable", lambda: (_ for _ in ()).throw(RuntimeError("verify failed")))

    assert applier.run() == 1
    assert stale.read_text(encoding="utf-8") == "obsolete"


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable modes are validated by the Linux CI job")
def test_update_applier_atomically_installs_executable_linux_mode(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    updater = tmp_path / "updater"
    staging = tmp_path / "staging"
    for directory in (source, destination, updater, staging):
        directory.mkdir()
    source_executable = source / "mcw-launcher"
    destination_executable = destination / "mcw-launcher"
    source_executable.write_bytes(b"new-linux")
    source_executable.chmod(0o755)
    destination_executable.write_bytes(b"old-linux")
    destination_executable.chmod(0o755)
    request = UpdateApplyRequest(
        parent_pid=123,
        source_directory=source,
        destination_directory=destination,
        executable_name="mcw-launcher",
        updater_directory=updater,
        staging_directory=staging,
        persistent_log_path=tmp_path / "updater.log",
        target_version="1.5.0-beta.2",
    )
    applier = UpdateApplier(request)
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda: None)

    assert applier.run() == 0
    assert destination_executable.read_bytes() == b"new-linux"
    assert destination_executable.stat().st_mode & 0o777 == 0o755
    assert not list(destination.glob(".*.mcw-update-*.tmp"))
