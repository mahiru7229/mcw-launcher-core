import json
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
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: starts.append(True))

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
    restored_flags: list[bool] = []
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_show_error", lambda _message, **_kwargs: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda **kwargs: (starts.append(True), restored_flags.append(bool(kwargs.get("restored")))))

    def fail_after_partial_copy() -> None:
        destination_exe.write_bytes(b"partial")
        raise RuntimeError("simulated copy failure")

    monkeypatch.setattr(applier, "_copy_update_files", fail_after_partial_copy)

    assert applier.run() == 1
    assert destination_exe.read_bytes() == b"old-exe"
    assert starts == [True]
    assert restored_flags == [True]
    log = request.persistent_log_path.read_text(encoding="utf-8")
    assert "Update failed: simulated copy failure" in log
    assert "Rollback completed" in log


def test_update_request_loads_and_validates_json(tmp_path) -> None:
    request = make_request(tmp_path)
    (request.source_directory / "MCW Launcher.exe").write_bytes(b"exe")
    request_path = request.updater_directory / "request.json"
    request_path.write_text(
        """{
  "schema_version": 2,
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
            "schema_version": 2,
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
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: None)

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
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: None)
    monkeypatch.setattr(applier, "_show_error", lambda _message, **_kwargs: None)
    monkeypatch.setattr(applier, "_verify_updated_executable", lambda: (_ for _ in ()).throw(RuntimeError("verify failed")))

    assert applier.run() == 1
    assert stale.read_text(encoding="utf-8") == "obsolete"


def test_update_applier_replaces_executable_before_other_files(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source_exe = request.source_directory / request.executable_name
    source_exe.write_bytes(b"new-exe")
    (request.source_directory / "lang").mkdir()
    (request.source_directory / "lang" / "en-US.json").write_text("new", encoding="utf-8")
    (request.destination_directory / request.executable_name).write_bytes(b"old-exe")

    applier = UpdateApplier(request)
    copied: list[Path] = []

    def record_copy(_source: Path, destination: Path) -> None:
        copied.append(destination.relative_to(request.destination_directory))

    monkeypatch.setattr(applier, "_copy_with_retry", record_copy)
    applier._copy_update_files()

    assert copied[0] == Path(request.executable_name)
    assert Path("lang/en-US.json") in copied[1:]


def test_copy_with_retry_retries_generic_atomic_replace_without_recopied_temp(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    # This test exercises the platform-neutral atomic-copy path. The launcher
    # executable intentionally takes the native Windows transition path on
    # Windows, so use an ordinary managed file here to keep the test generic
    # on every CI runner.
    source = request.source_directory / "lang" / "en-US.json"
    destination = request.destination_directory / "lang" / "en-US.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"new-language")
    destination.write_bytes(b"old-language")
    applier = UpdateApplier(request)

    real_replace = os.replace
    replace_calls = 0
    copy_calls = 0

    def fake_copy2(src, dst, *args, **kwargs):
        nonlocal copy_calls
        copy_calls += 1
        return __import__("shutil").copyfile(src, dst)

    def flaky_replace(src, dst):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls < 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr("src.core.update.update_applier.shutil.copy2", fake_copy2)
    monkeypatch.setattr("src.core.update.update_applier.os.replace", flaky_replace)
    monkeypatch.setattr("src.core.update.update_applier.time.sleep", lambda _seconds: None)

    applier._copy_with_retry(source, destination)

    assert destination.read_bytes() == b"new-language"
    assert replace_calls == 3
    assert copy_calls == 1


def test_rollback_skips_unchanged_locked_executable(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source_exe = request.source_directory / request.executable_name
    destination_exe = request.destination_directory / request.executable_name
    source_exe.write_bytes(b"new-exe")
    destination_exe.write_bytes(b"old-exe")
    applier = UpdateApplier(request)
    applier._backup_existing_files()

    restored: list[Path] = []
    monkeypatch.setattr(applier, "_copy_with_retry", lambda _src, dst: restored.append(dst))
    applier._restore_backup()

    assert restored == []
    assert destination_exe.read_bytes() == b"old-exe"


def test_update_applier_does_not_restart_when_rollback_fails(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    (request.source_directory / request.executable_name).write_bytes(b"new-exe")
    (request.destination_directory / request.executable_name).write_bytes(b"old-exe")
    applier = UpdateApplier(request)
    starts: list[bool] = []
    shown: list[tuple[str, bool]] = []

    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_copy_update_files", lambda: (_ for _ in ()).throw(RuntimeError("copy failed")))
    monkeypatch.setattr(applier, "_restore_backup", lambda: (_ for _ in ()).throw(RuntimeError("rollback failed")))
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: starts.append(True))
    monkeypatch.setattr(applier, "_show_error", lambda message, *, rollback_completed=True: shown.append((message, rollback_completed)))

    assert applier.run() == 1
    assert starts == []
    assert shown == [("copy failed", False)]
    log = request.persistent_log_path.read_text(encoding="utf-8")
    assert "Rollback failed: rollback failed" in log
    assert "Launcher was not restarted because rollback did not complete safely" in log


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
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: None)

    assert applier.run() == 0
    assert destination_executable.read_bytes() == b"new-linux"
    assert destination_executable.stat().st_mode & 0o777 == 0o755
    assert not list(destination.glob(".*.mcw-update-*.tmp"))


def test_update_applier_cleanup_paths_removes_old_docs_without_error(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    (request.source_directory / request.executable_name).write_bytes(b"new-exe")
    (request.destination_directory / request.executable_name).write_bytes(b"old-exe")
    docs = request.destination_directory / "docs"
    docs.mkdir()
    (docs / "old.md").write_text("legacy docs", encoding="utf-8")
    (request.source_directory / "mcw-update.json").write_text(json.dumps({
        "schema_version": 2,
        "version": "1.5.1-beta.6",
        "platform": "windows-x64",
        "executable": request.executable_name,
        "files": [request.executable_name, "mcw-update.json"],
        "cleanup_paths": ["docs"],
    }), encoding="utf-8")

    applier = UpdateApplier(request)
    monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
    monkeypatch.setattr(applier, "_start_launcher", lambda **_kwargs: None)

    assert applier.run() == 0
    assert not docs.exists()


def test_windows_release_gate_waits_for_matching_processes_without_false_unlock_probe(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    request = make_request(tmp_path)
    executable = request.destination_directory / request.executable_name
    executable.write_bytes(b"old-exe")
    applier = UpdateApplier(request)

    process_states = iter([[501, 502], [], []])
    monkeypatch.setattr(
        "src.core.update.update_applier.PlatformInfo.current",
        lambda: SimpleNamespace(os_name="windows"),
    )
    monkeypatch.setattr(applier, "_matching_windows_processes", lambda _path: next(process_states))
    monkeypatch.setattr(applier, "WINDOWS_RELEASE_POLL_SECONDS", 0)
    monkeypatch.setattr(applier, "WINDOWS_SETTLE_SECONDS", 0)

    applier._wait_for_launcher_release(timeout_seconds=1.0)

    log = request.persistent_log_path.read_text(encoding="utf-8")
    assert "Detected remaining launcher process(es) for this installation: 501, 502" in log
    assert "No launcher process remains; Windows replacement transaction may begin" in log
    assert "executable lock is released" not in log


def test_windows_release_gate_times_out_before_transaction_when_process_remains(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    request = make_request(tmp_path)
    executable = request.destination_directory / request.executable_name
    executable.write_bytes(b"old-exe")
    applier = UpdateApplier(request)

    monkeypatch.setattr(
        "src.core.update.update_applier.PlatformInfo.current",
        lambda: SimpleNamespace(os_name="windows"),
    )
    monkeypatch.setattr(applier, "_matching_windows_processes", lambda _path: [501])
    monkeypatch.setattr(applier, "WINDOWS_RELEASE_POLL_SECONDS", 0)
    monkeypatch.setattr(applier, "WINDOWS_SETTLE_SECONDS", 0)

    with pytest.raises(TimeoutError, match="update was not started"):
        applier._wait_for_launcher_release(timeout_seconds=0.0)


def test_windows_launcher_replace_uses_rename_away_fallback(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source = request.source_directory / request.executable_name
    destination = request.destination_directory / request.executable_name
    source.write_bytes(b"new-exe")
    destination.write_bytes(b"old-exe")
    applier = UpdateApplier(request)

    monkeypatch.setattr(applier, "_windows_file_attributes", lambda _path: None)
    monkeypatch.setattr(applier, "_windows_replace_existing", lambda _src, _dst: (False, "MoveFileExW(REPLACE_EXISTING)", 5))

    moves: list[tuple[str, str]] = []
    def fake_move(src: Path, dst: Path, *, replace_existing: bool):
        moves.append((src.name, dst.name))
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return True, 0

    monkeypatch.setattr(applier, "_windows_move_file", fake_move)
    applier._copy_windows_launcher_with_retry(source, destination)

    assert destination.read_bytes() == b"new-exe"
    assert len(moves) == 2
    assert moves[0][0] == request.executable_name
    assert moves[1][1] == request.executable_name
    log = request.persistent_log_path.read_text(encoding="utf-8")
    assert "Direct launcher replacement blocked" in log
    assert "using Windows rename-away fallback" in log
    assert "installed successfully after rename-away fallback" in log


def test_windows_rename_away_restores_old_launcher_when_new_install_fails(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source = request.source_directory / request.executable_name
    destination = request.destination_directory / request.executable_name
    source.write_bytes(b"new-exe")
    destination.write_bytes(b"old-exe")
    applier = UpdateApplier(request)
    applier.EXECUTABLE_REPLACE_RETRIES = 1

    monkeypatch.setattr(applier, "_windows_file_attributes", lambda _path: None)
    monkeypatch.setattr(applier, "_windows_replace_existing", lambda _src, _dst: (False, "MoveFileExW(REPLACE_EXISTING)", 5))

    call = 0
    def fake_move(src: Path, dst: Path, *, replace_existing: bool):
        nonlocal call
        call += 1
        if call == 1:  # old launcher -> retired
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            return True, 0
        if call == 2:  # new launcher -> public path fails
            return False, 32
        if call == 3:  # retired -> public path must restore
            os.replace(src, dst)
            return True, 0
        raise AssertionError("unexpected move")

    monkeypatch.setattr(applier, "_windows_move_file", fake_move)
    with pytest.raises(RuntimeError, match="Could not transition Windows launcher executable"):
        applier._copy_windows_launcher_with_retry(source, destination)

    assert destination.read_bytes() == b"old-exe"


def test_windows_launcher_replace_clears_and_restores_readonly_on_failure(tmp_path, monkeypatch) -> None:
    request = make_request(tmp_path)
    source = request.source_directory / request.executable_name
    destination = request.destination_directory / request.executable_name
    source.write_bytes(b"new-exe")
    destination.write_bytes(b"old-exe")
    applier = UpdateApplier(request)
    applier.EXECUTABLE_REPLACE_RETRIES = 1

    attributes_written: list[int] = []
    monkeypatch.setattr(applier, "_windows_file_attributes", lambda _path: 0x21)  # ARCHIVE | READONLY
    monkeypatch.setattr(applier, "_windows_set_file_attributes", lambda _path, attrs: attributes_written.append(attrs) or True)
    monkeypatch.setattr(applier, "_windows_replace_existing", lambda _src, _dst: (False, "MoveFileExW(REPLACE_EXISTING)", 5))
    monkeypatch.setattr(applier, "_windows_move_file", lambda _src, _dst, *, replace_existing: (False, 5))

    with pytest.raises(RuntimeError):
        applier._copy_windows_launcher_with_retry(source, destination)

    assert attributes_written == [0x20, 0x21]
    assert destination.read_bytes() == b"old-exe"


def test_non_windows_release_gate_skips_windows_process_scan(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    request = make_request(tmp_path)
    (request.destination_directory / request.executable_name).write_bytes(b"old-exe")
    applier = UpdateApplier(request)

    monkeypatch.setattr(
        "src.core.update.update_applier.PlatformInfo.current",
        lambda: SimpleNamespace(os_name="linux"),
    )
    monkeypatch.setattr(
        applier,
        "_matching_windows_processes",
        lambda _path: (_ for _ in ()).throw(AssertionError("Windows scan must not run on Linux")),
    )

    applier._wait_for_launcher_release(timeout_seconds=0.0)
