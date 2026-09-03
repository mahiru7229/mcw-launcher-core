import json
import os
from pathlib import Path

import pytest

from src.core.update.linux_update_installer import LinuxUpdateInstaller
from src.core.update.update_errors import AutomaticUpdateUnsupportedError
from src.models.update.update_info import PreparedUpdate, ReleaseAsset, UpdateInfo


pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux updater tests require POSIX file modes and symlinks")


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
    executable = destination / "mcw-launcher"
    executable.write_bytes(b"old-linux")
    executable.chmod(0o755)
    incoming = source / executable.name
    incoming.write_bytes(b"new-linux")
    incoming.chmod(0o755)
    info = UpdateInfo(
        current_version="1.5.0-beta.1",
        version="1.5.0-beta.2",
        tag_name="v1.5.0-beta.2",
        title="Beta 2",
        release_notes="notes",
        release_url="https://example.invalid/release",
        published_at="2026-08-28T00:00:00Z",
        prerelease=True,
        asset=ReleaseAsset(name="linux.zip", download_url="https://example.invalid/linux.zip", size=1),
    )
    return PreparedUpdate(info, tmp_path / "linux.zip", tmp_path / "staging", source), destination, executable


def test_linux_installer_copies_helper_and_writes_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(LinuxUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.linux_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(LinuxUpdateInstaller, "_start_updater_process", staticmethod(lambda updater_executable, request_path, target: FakeProcess()))
    monkeypatch.setattr(LinuxUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)

    request_path = LinuxUpdateInstaller.launch(
        prepared,
        install_directory=destination,
        executable_path=executable,
        parent_pid=456,
        persistent_log_path=tmp_path / "updater.log",
    )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    helper = request_path.parent / "mcw-launcher-updater"
    assert request["parent_pid"] == 456
    assert request["target_version"] == "1.5.0-beta.2"
    assert helper.read_bytes() == b"old-linux"
    assert helper.stat().st_mode & 0o777 == 0o700


def test_linux_installer_keeps_launcher_open_when_helper_exits_early(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    updater_root = tmp_path / "temp"
    updater_root.mkdir()
    monkeypatch.setattr(LinuxUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.linux_update_installer.tempfile.gettempdir", lambda: str(updater_root))
    monkeypatch.setattr(LinuxUpdateInstaller, "_start_updater_process", staticmethod(lambda updater_executable, request_path, target: FakeProcess(2)))
    monkeypatch.setattr(LinuxUpdateInstaller, "STARTUP_GRACE_SECONDS", 0)

    with pytest.raises(RuntimeError, match="exited before the launcher closed"):
        LinuxUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable)

    assert not any(updater_root.iterdir())


def test_linux_installer_refuses_unwritable_install_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    monkeypatch.setattr(LinuxUpdateInstaller, "is_supported", staticmethod(lambda: True))
    monkeypatch.setattr("src.core.update.linux_update_installer.os.open", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))

    with pytest.raises(AutomaticUpdateUnsupportedError, match="will not request sudo"):
        LinuxUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable)


def test_linux_installer_refuses_symlinked_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepared, destination, executable = make_prepared(tmp_path)
    real_executable = destination / "real-launcher"
    executable.rename(real_executable)
    executable.symlink_to(real_executable.name)
    monkeypatch.setattr(LinuxUpdateInstaller, "is_supported", staticmethod(lambda: True))

    with pytest.raises(RuntimeError, match="symbolic link"):
        LinuxUpdateInstaller.launch(prepared, install_directory=destination, executable_path=executable)
