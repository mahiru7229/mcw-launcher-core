from pathlib import Path

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
    info = UpdateInfo(
        current_version="0.5.0-beta.2",
        version="0.5.0-beta.3",
        tag_name="v0.5.0-beta.3",
        title="Beta 3",
        release_notes="notes",
        release_url="https://example.invalid/release",
        published_at="2026-07-15T00:00:00Z",
        prerelease=True,
        asset=ReleaseAsset(name="release.zip", download_url="https://example.invalid/release.zip", size=1),
    )
    prepared = PreparedUpdate(info=info, archive_path=tmp_path / "release.zip", staging_directory=tmp_path / "staging", content_directory=source)
    return prepared, destination, executable


def test_installer_copies_current_exe_and_writes_request(tmp_path, monkeypatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(WindowsUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.windows_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(WindowsUpdateInstaller, "_start_updater_process", classmethod(lambda cls, updater_executable, request_path, target: FakeProcess()))
    monkeypatch.setattr(WindowsUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)

    request_path = WindowsUpdateInstaller.launch(
        prepared,
        install_directory=destination,
        executable_path=executable,
        parent_pid=456,
        persistent_log_path=destination / "logs" / "updater.log",
    )

    assert request_path.is_file()
    assert (request_path.parent / "MCW Launcher Updater.exe").read_bytes() == b"old"
    text = request_path.read_text(encoding="utf-8")
    assert '"parent_pid": 456' in text
    assert '"target_version": "0.5.0-beta.3"' in text


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
