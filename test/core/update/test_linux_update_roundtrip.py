import hashlib
import os
from pathlib import Path
import shutil

import pytest

from src.core.fs.paths import Paths
from src.core.update.update_applier import UpdateApplier, UpdateApplyRequest
from src.core.update.update_manager import UpdateManager
from src.models.update.update_info import ReleaseAsset, UpdateInfo
from tools.build_release_zip import build_release_zip


pytestmark = pytest.mark.skipif(os.name == "nt", reason="Linux update roundtrip requires POSIX executable modes")


def test_packaged_beta1_to_beta2_linux_update_roundtrip_preserves_user_data(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("Beta 2", encoding="utf-8")
    (project / "LICENSE").write_text("MIT", encoding="utf-8")
    executable = project / "mcw-launcher"
    executable.write_bytes(b"beta-2-linux-binary")
    executable.chmod(0o755)
    package = tmp_path / "MCW-Launcher-v1.5.0-beta.2-linux-x64.zip"
    build_release_zip(project, executable, "1.5.0-beta.2", package, "linux-x64")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    info = UpdateInfo(
        current_version="1.5.0-beta.1",
        version="1.5.0-beta.2",
        tag_name="v1.5.0-beta.2",
        title="Beta 2",
        release_notes="roundtrip",
        release_url="https://example.invalid/beta2",
        published_at="2026-08-28T00:00:00Z",
        prerelease=True,
        asset=ReleaseAsset(package.name, "https://example.invalid/beta2.zip", package.stat().st_size, digest),
    )

    with Paths.configured(tmp_path / "xdg-test-root"):
        user_world = Paths.INSTANCES_ROOT / "survival" / "saves" / "World" / "level.dat"
        user_world.parent.mkdir(parents=True)
        user_world.write_bytes(b"user-world")
        cached_package = Paths.update_download_path(info.tag_name, info.asset.name)
        cached_package.parent.mkdir(parents=True)
        shutil.copy2(package, cached_package)
        prepared = UpdateManager(
            "example/repo",
            "1.5.0-beta.1",
            channel="beta",
            platform_id="linux-x64",
        ).prepare_update(info)

        install = tmp_path / "install"
        install.mkdir()
        installed_executable = install / "mcw-launcher"
        installed_executable.write_bytes(b"beta-1-linux-binary")
        installed_executable.chmod(0o755)
        request = UpdateApplyRequest(
            parent_pid=123,
            source_directory=prepared.content_directory,
            destination_directory=install,
            executable_name="mcw-launcher",
            updater_directory=tmp_path / "updater",
            staging_directory=prepared.staging_directory,
            persistent_log_path=Paths.LOGS_ROOT / "updater.log",
            target_version=info.version,
        )
        request.updater_directory.mkdir()
        applier = UpdateApplier(request)
        monkeypatch.setattr(applier, "_wait_for_process_exit", lambda _pid: None)
        monkeypatch.setattr(applier, "_start_launcher", lambda: None)

        assert applier.run() == 0
        assert installed_executable.read_bytes() == b"beta-2-linux-binary"
        assert installed_executable.stat().st_mode & 0o777 == 0o755
        assert user_world.read_bytes() == b"user-world"
        assert not prepared.staging_directory.exists()
