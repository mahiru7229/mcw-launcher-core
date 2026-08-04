from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from src.core.fs.paths import Paths
from src.models.update.update_info import PreparedUpdate


class AutomaticUpdateUnsupportedError(RuntimeError):
    pass


class WindowsUpdateInstaller:
    STARTUP_GRACE_SECONDS = 1.0

    @staticmethod
    def is_supported() -> bool:
        return os.name == "nt" and bool(getattr(sys, "frozen", False))

    @classmethod
    def launch(cls, prepared: PreparedUpdate, install_directory: Path | None = None, executable_path: Path | None = None, parent_pid: int | None = None, persistent_log_path: Path | None = None) -> Path:
        if not cls.is_supported():
            raise AutomaticUpdateUnsupportedError("Automatic installation is only available in the packaged Windows launcher.")

        executable = Path(executable_path) if executable_path is not None else Path(sys.executable)
        destination = Path(install_directory) if install_directory is not None else executable.resolve().parent
        source = prepared.content_directory.resolve()
        destination = destination.resolve()
        executable = executable.resolve()
        persistent_log = Path(persistent_log_path) if persistent_log_path is not None else Paths.updater_log_path()
        persistent_log = persistent_log.resolve()

        cls._validate_paths(source, destination, executable)

        updater_directory = Path(tempfile.gettempdir()) / f"mcw-launcher-updater-{uuid.uuid4().hex}"
        updater_directory.mkdir(parents=True, exist_ok=False)
        updater_executable = updater_directory / "MCW Launcher Updater.exe"
        request_path = updater_directory / "update-request.json"

        try:
            shutil.copy2(executable, updater_executable)
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
            process = cls._start_updater_process(updater_executable, request_path, destination)
            time.sleep(cls.STARTUP_GRACE_SECONDS)
            exit_code = process.poll()
            if exit_code is not None:
                detail = cls._read_startup_error(updater_directory, persistent_log)
                raise RuntimeError(f"The updater process exited before the launcher closed (code {exit_code}).{detail}")
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
        if not (source / executable.name).is_file():
            raise RuntimeError(f"The update ZIP does not contain the expected executable: {executable.name}")

    @classmethod
    def _start_updater_process(cls, updater_executable: Path, request_path: Path, destination: Path) -> subprocess.Popen:
        command = [str(updater_executable), "--apply-update", str(request_path)]
        base_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        breakaway_flag = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)

        kwargs = {
            "cwd": str(destination),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if breakaway_flag:
            try:
                return subprocess.Popen(command, creationflags=base_flags | breakaway_flag, **kwargs)
            except OSError:
                pass
        return subprocess.Popen(command, creationflags=base_flags, **kwargs)

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
