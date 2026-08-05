from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import zipfile

from src.core.diagnostics import diagnostics_manager
from src.core.diagnostics.diagnostics_manager import DiagnosticsManager
from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_run_lock import InstanceRunLock


def test_build_report_contains_safe_runtime_information(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(Paths, "LOGS_ROOT", tmp_path / "logs")
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [SimpleNamespace(name="One")])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [SimpleNamespace(name="One", state="running", minecraft_pid=123, launcher_pid=10)])

    report = DiagnosticsManager.build_report("0.5.0-beta.3", settings={"gui": {"language": "vi-VN"}, "secret": {"token": "nope"}}, activity_log="hello")

    assert "launcher_version: 0.5.0-beta.3" in report
    assert "running_instance: One [running] pid=123" in report
    assert '"language": "vi-VN"' in report
    assert "token" not in report
    assert "hello" in report


def test_write_report_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [])
    destination = tmp_path / "diagnostics.txt"

    result = DiagnosticsManager.write_report(destination, "0.5.0-beta.3")

    assert result == destination
    assert destination.is_file()
    assert not destination.with_name("diagnostics.txt.tmp").exists()


def test_build_report_redacts_tokens_from_activity_log(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", tmp_path / "accounts")
    monkeypatch.setattr(Paths, "LOGS_ROOT", tmp_path / "logs")
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [])

    report = DiagnosticsManager.build_report(
        "0.5.0-beta.10",
        activity_log="Authorization: Bearer secret-token refresh_token=refresh-secret&code=oauth-code",
    )

    assert "secret-token" not in report
    assert "refresh-secret" not in report
    assert "oauth-code" not in report
    assert "<redacted>" in report


def test_write_bundle_is_bounded_redacted_and_self_verifying(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    accounts = tmp_path / "accounts"
    logs.mkdir()
    accounts.mkdir()
    (logs / "launcher.log").write_text(
        "normal line\nAuthorization: Bearer secret-token\nrefresh_token=refresh-secret\n",
        encoding="utf-8",
    )
    (accounts / "accounts.json").write_text('{"access_token":"must-not-ship"}', encoding="utf-8")
    monkeypatch.setattr(Paths, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "ACCOUNTS_ROOT", accounts)
    monkeypatch.setattr(Paths, "LOGS_ROOT", logs)
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [])
    monkeypatch.setattr(
        diagnostics_manager.download_recovery_manager,
        "inspect",
        lambda: SimpleNamespace(items=(), resumable_count=0),
    )
    destination = tmp_path / "support"

    result = DiagnosticsManager.write_bundle(
        destination,
        "0.9.0-beta.6",
        activity_log="code=oauth-secret",
    )

    assert result == destination.with_suffix(".zip")
    assert result.is_file()
    assert not result.with_suffix(".zip.part").exists()
    with zipfile.ZipFile(result, "r") as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {
            "report.txt",
            "download-recovery.json",
            "instance-health.json",
            "process-sessions.json",
            "operation-journals.json",
            "manifest.json",
        } <= names
        assert any(name.startswith("logs/") for name in names)
        assert not any("account" in name.casefold() for name in names)
        combined = b"\n".join(archive.read(name) for name in names)
        assert b"secret-token" not in combined
        assert b"refresh-secret" not in combined
        assert b"oauth-secret" not in combined
        assert b"must-not-ship" not in combined
        assert b"<redacted>" in combined

        manifest = json.loads(archive.read("manifest.json"))
        for entry in manifest["entries"]:
            payload = archive.read(entry["path"])
            assert entry["size"] == len(payload)
            assert entry["sha256"] == hashlib.sha256(payload).hexdigest()


def test_bundle_limits_log_count_and_uses_log_tails(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    for index in range(DiagnosticsManager.MAX_LOG_FILES + 3):
        (logs / f"{index:02d}.log").write_bytes(
            b"old-" + (b"x" * DiagnosticsManager.MAX_LOG_BYTES) + f"-tail-{index}".encode()
        )
    monkeypatch.setattr(Paths, "LOGS_ROOT", logs)
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [])
    monkeypatch.setattr(
        diagnostics_manager.download_recovery_manager,
        "inspect",
        lambda: SimpleNamespace(items=(), resumable_count=0),
    )

    result = DiagnosticsManager.write_bundle(tmp_path / "bounded.zip", "0.9.0-beta.6")

    with zipfile.ZipFile(result, "r") as archive:
        log_names = [name for name in archive.namelist() if name.startswith("logs/")]
        assert len(log_names) == DiagnosticsManager.MAX_LOG_FILES
        assert all(len(archive.read(name)) <= DiagnosticsManager.MAX_LOG_BYTES + 64 for name in log_names)
        assert all(b"[log tail truncated]" in archive.read(name) for name in log_names)



def test_bundle_marks_invalid_operation_journals_without_leaking_content(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    instances = tmp_path / "instances"
    operations = instances / ".runtime" / "operations"
    operations.mkdir(parents=True)
    (operations / "broken.json").write_text('{"access_token":"secret-token"', encoding="utf-8")
    monkeypatch.setattr(Paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances)
    monkeypatch.setattr(Paths, "LOGS_ROOT", logs)
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])
    monkeypatch.setattr(InstanceRunLock, "list_active", lambda: [])
    monkeypatch.setattr(diagnostics_manager.ProcessSupervisor, "list_active", lambda: ())
    monkeypatch.setattr(diagnostics_manager.download_recovery_manager, "inspect", lambda: SimpleNamespace(items=(), resumable_count=0))

    result = DiagnosticsManager.write_bundle(tmp_path / "invalid-journal.zip", "0.12.0-beta.8")

    with zipfile.ZipFile(result, "r") as archive:
        payload = json.loads(archive.read("operation-journals.json"))
        assert payload["journals"] == [{"journal": "broken.json", "state": "invalid"}]
        assert b"secret-token" not in archive.read("operation-journals.json")


def test_instance_health_bundle_uses_safe_relative_paths(tmp_path, monkeypatch):
    from src.models.instance.instance_health import InstanceHealthIssue, InstanceHealthReport, InstanceHealthSeverity, InstanceHealthState

    instances = tmp_path / "instances"
    instance_dir = instances / "Example"
    instance_dir.mkdir(parents=True)
    monkeypatch.setattr(Paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances)
    monkeypatch.setattr(
        diagnostics_manager.InstanceHealthManager,
        "list",
        lambda _instances: [
            InstanceHealthReport(
                instance_id="id",
                name="Example",
                state=InstanceHealthState.MISSING_FILES,
                issues=(
                    InstanceHealthIssue(
                        code="missing",
                        state=InstanceHealthState.MISSING_FILES,
                        severity=InstanceHealthSeverity.ERROR,
                        message="Missing file",
                        path=instance_dir / "mods" / "missing.jar",
                    ),
                ),
                checked_at="now",
            )
        ],
    )
    monkeypatch.setattr(InstanceManager, "list_instances", lambda: [])

    payload = json.loads(DiagnosticsManager._instance_health_json())

    assert payload["instances"][0]["issues"][0]["path"] == "instances/Example/mods/missing.jar"
    assert str(tmp_path) not in json.dumps(payload)
