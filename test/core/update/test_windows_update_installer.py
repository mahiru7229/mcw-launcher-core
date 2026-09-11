from pathlib import Path
import json

import pytest

from src.core.update.windows_update_installer import WindowsUpdateInstaller
from src.models.update.update_info import PreparedUpdate, ReleaseAsset, UpdateInfo


class FakeProcess:
    def __init__(self, exit_code=None) -> None:
        self.exit_code = exit_code

    def poll(self):
        return self.exit_code


def make_prepared(tmp_path: Path) -> tuple[PreparedUpdate, Path, Path]:
    destination = tmp_path / "launcher"
    source = tmp_path / "staging" / "extracted" / "release"
    destination.mkdir(parents=True)
    source.mkdir(parents=True)
    executable = destination / "MCW Launcher.exe"
    executable.write_bytes(b"old")
    (source / executable.name).write_bytes(b"new")
    bundled = source / "updater" / "MCW Updater.exe"
    bundled.parent.mkdir()
    bundled.write_bytes(b"new-updater")
    (source / "mcw-update.json").write_text(json.dumps({
        "schema_version": 2,
        "version": "1.5.1-beta.6",
        "platform": "windows-x64",
        "executable": "MCW Launcher.exe",
        "updater": "updater/MCW Updater.exe",
        "files": ["MCW Launcher.exe", "updater/MCW Updater.exe", "mcw-update.json"],
    }), encoding="utf-8")
    info = UpdateInfo(
        current_version="1.5.1-beta.4",
        version="1.5.1-beta.6",
        tag_name="v1.5.1-beta.6",
        title="Beta 5",
        release_notes="notes",
        release_url="https://example.invalid/release",
        published_at="2026-09-10T00:00:00Z",
        prerelease=True,
        asset=ReleaseAsset(name="release.zip", download_url="https://example.invalid/release.zip", size=1),
    )
    prepared = PreparedUpdate(info=info, archive_path=tmp_path / "release.zip", staging_directory=tmp_path / "staging", content_directory=source)
    return prepared, destination, executable


def test_installer_copies_incoming_bundled_updater_and_writes_schema2_request(tmp_path, monkeypatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(WindowsUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.windows_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(WindowsUpdateInstaller, "_start_updater_process", classmethod(lambda cls, updater_executable, request_path, target: FakeProcess()))
    monkeypatch.setattr(WindowsUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(WindowsUpdateInstaller, "_wait_for_ready", classmethod(lambda cls, process, ready_path, timeout_seconds: True))

    request_path = WindowsUpdateInstaller.launch(
        prepared,
        install_directory=destination,
        executable_path=executable,
        parent_pid=456,
        persistent_log_path=destination / "logs" / "updater.log",
    )

    assert request_path.is_file()
    assert (request_path.parent / "MCW Updater.exe").read_bytes() == b"new-updater"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["schema_version"] == 2
    assert request["parent_pid"] == 456
    assert request["target_version"] == "1.5.1-beta.6"


def test_installer_refuses_package_without_bundled_updater(tmp_path, monkeypatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    (prepared.content_directory / "updater" / "MCW Updater.exe").unlink()
    monkeypatch.setattr(WindowsUpdateInstaller, "is_supported", staticmethod(lambda: True))

    with pytest.raises(RuntimeError, match="bundled updater is missing"):
        WindowsUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable)


def test_installer_never_falls_back_to_current_launcher_as_updater(tmp_path, monkeypatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    incoming = prepared.content_directory / "updater" / "MCW Updater.exe"
    incoming.write_bytes(b"incoming-vnext-updater")
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(WindowsUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.windows_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(WindowsUpdateInstaller, "_start_updater_process", classmethod(lambda cls, updater_executable, request_path, target: FakeProcess()))
    monkeypatch.setattr(WindowsUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(WindowsUpdateInstaller, "_wait_for_ready", classmethod(lambda cls, process, ready_path, timeout_seconds: True))

    request_path = WindowsUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable, parent_pid=456)

    copied = request_path.parent / "MCW Updater.exe"
    assert copied.read_bytes() == b"incoming-vnext-updater"
    assert copied.read_bytes() != executable.read_bytes()


def test_installer_keeps_launcher_open_when_updater_exits_early(tmp_path, monkeypatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(WindowsUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.windows_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(WindowsUpdateInstaller, "_start_updater_process", classmethod(lambda cls, updater_executable, request_path, target: FakeProcess(2)))
    monkeypatch.setattr(WindowsUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)

    with pytest.raises(RuntimeError, match="exited before the launcher closed"):
        WindowsUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable, parent_pid=456)

    assert not any(updater_root.iterdir())
