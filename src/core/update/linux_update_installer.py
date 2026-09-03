from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

from src.core.fs.paths import Paths
from src.core.system.platform_info import PlatformInfo
from src.core.update.update_errors import AutomaticUpdateUnsupportedError
from src.models.update.update_info import PreparedUpdate


class LinuxUpdateInstaller:
    """Start a detached copy of the packaged launcher to apply a Linux update."""

    STARTUP_GRACE_SECONDS = 1.0

    @staticmethod
    def is_supported() -> bool:
        profile = PlatformInfo.current()
        return profile.os_name == "linux" and profile.architecture == "x64" and bool(getattr(sys, "frozen", False))

    @classmethod
    def launch(
        cls,
        prepared: PreparedUpdate,
        install_directory: Path | None = None,
        executable_path: Path | None = None,
        parent_pid: int | None = None,
        persistent_log_path: Path | None = None,
    ) -> Path:
        if not cls.is_supported():
            raise AutomaticUpdateUnsupportedError(
                "Automatic installation is only available in the packaged Linux x64 launcher."
            )

        requested_executable = Path(executable_path) if executable_path is not None else Path(sys.executable)
        executable = requested_executable.parent.resolve() / requested_executable.name
        destination = Path(install_directory) if install_directory is not None else executable.parent
        source = prepared.content_directory.resolve()
        destination = destination.resolve()
        persistent_log = Path(persistent_log_path) if persistent_log_path is not None else Paths.updater_log_path()
        persistent_log = persistent_log.resolve()

        cls._validate_paths(source, destination, executable)
        cls._verify_write_access(destination)

        updater_directory = Path(tempfile.gettempdir()) / f"mcw-launcher-updater-{uuid.uuid4().hex}"
        updater_directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        updater_executable = updater_directory / "mcw-launcher-updater"
        request_path = updater_directory / "update-request.json"

        try:
            shutil.copy2(executable, updater_executable)
            updater_executable.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            request = {
                "schema_version": 1,
                "parent_pid": int(parent_pid if parent_pid is not None else os.getpid()),
                "source_directory": str(source),
                "destination_directory": str(destination),
                "executable_name": executable.name,
                "updater_directory": str(updater_directory),
                "staging_directory": str(prepared.staging_directory.resolve()),
                "persistent_log_path": str(persistent_log),
                "target_version": str(prepared.info.version),
            }
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            request_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            process = cls._start_updater_process(updater_executable, request_path, destination)
            time.sleep(cls.STARTUP_GRACE_SECONDS)
            exit_code = process.poll()
            if exit_code is not None:
                detail = cls._read_startup_error(updater_directory, persistent_log)
                raise RuntimeError(
                    f"The Linux updater process exited before the launcher closed (code {exit_code}).{detail}"
                )
            return request_path
        except Exception:
            shutil.rmtree(updater_directory, ignore_errors=True)
            raise

    @staticmethod
    def _validate_paths(source: Path, destination: Path, executable: Path) -> None:
        if not source.is_dir():
            raise FileNotFoundError(f"Prepared update directory does not exist: {source}")
        if not destination.is_dir():
            raise FileNotFoundError(f"Launcher directory does not exist: {destination}")
        if executable.parent != destination:
            raise RuntimeError("The launcher executable must be inside the installation directory.")
        if not executable.is_file() or executable.is_symlink():
            raise RuntimeError("The current Linux launcher must be a regular file, not a symbolic link.")
        incoming = source / executable.name
        if not incoming.is_file() or incoming.is_symlink():
            raise RuntimeError(f"The update ZIP does not contain a regular {executable.name} executable.")
        if incoming.stat().st_mode & 0o111 == 0:
            raise RuntimeError("The Linux launcher in the update ZIP is not executable.")

    @staticmethod
    def _verify_write_access(destination: Path) -> None:
        probe = destination / f".mcw-update-write-test-{uuid.uuid4().hex}"
        try:
            descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            probe.unlink()
        except OSError as error:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            raise AutomaticUpdateUnsupportedError(
                "The launcher installation directory is not writable. Reinstall it in your Home directory or update it manually; MCW Launcher will not request sudo."
            ) from error

    @staticmethod
    def _start_updater_process(
        updater_executable: Path,
        request_path: Path,
        destination: Path,
    ) -> subprocess.Popen:
        return subprocess.Popen(
            [str(updater_executable), "--apply-update", str(request_path)],
            cwd=str(destination),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )

    @staticmethod
    def _read_startup_error(updater_directory: Path, persistent_log: Path) -> str:
        for log_path in (updater_directory / "update.log", persistent_log):
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace").strip()
                if text:
                    return f" Last updater log: {text.splitlines()[-1]}"
            except OSError:
                continue
        return ""
