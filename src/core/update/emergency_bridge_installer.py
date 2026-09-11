from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from src.core.system.platform_info import PlatformInfo
from src.core.update.update_errors import AutomaticUpdateUnsupportedError
from src.models.update.update_info import PreparedUpdate


class EmergencyBridgeInstaller:
    """Launch a maintainer-authorized recovery bridge downloaded from a release."""

    STARTUP_GRACE_SECONDS = 1.0

    @staticmethod
    def is_supported() -> bool:
        profile = PlatformInfo.current()
        return profile.os_name in {"windows", "linux"} and profile.architecture == "x64" and bool(getattr(sys, "frozen", False))

    @classmethod
    def launch(
        cls,
        prepared: PreparedUpdate,
        install_directory: Path | None = None,
        executable_path: Path | None = None,
        parent_pid: int | None = None,
        persistent_log_path: Path | None = None,
    ) -> Path:
        del parent_pid, persistent_log_path
        if prepared.info.install_strategy != "bridge":
            raise RuntimeError("Emergency bridge installer received a normal updater package.")
        if not cls.is_supported():
            raise AutomaticUpdateUnsupportedError("Emergency bridge updates require a packaged Windows/Linux x64 launcher.")

        current_executable = Path(executable_path) if executable_path is not None else Path(sys.executable)
        destination = Path(install_directory) if install_directory is not None else current_executable.resolve().parent
        destination = destination.resolve()
        source = prepared.archive_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Prepared MCW Update Bridge does not exist: {source}")

        profile = PlatformInfo.current()
        suffix = ".exe" if profile.os_name == "windows" else ""
        helper_root = Path(tempfile.gettempdir()) / f"mcw-launcher-bridge-{uuid.uuid4().hex}"
        helper_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        helper = helper_root / f"MCW Update Bridge{suffix}"
        try:
            shutil.copy2(source, helper)
            if profile.os_name == "linux":
                helper.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            process = cls._start(helper, destination, prepared.info.tag_name)
            time.sleep(cls.STARTUP_GRACE_SECONDS)
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"MCW Update Bridge exited before launcher handoff (code {code}).")
            return helper
        except Exception:
            shutil.rmtree(helper_root, ignore_errors=True)
            raise

    @staticmethod
    def _start(helper: Path, destination: Path, tag_name: str) -> subprocess.Popen:
        command = [
            str(helper),
            "--install-dir", str(destination),
            "--tag", str(tag_name),
            "--force-close",
            "--cli",
        ]
        kwargs = {
            "cwd": str(destination),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(command, **kwargs)
