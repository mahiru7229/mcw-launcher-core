from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Callable


@dataclass(frozen=True, slots=True)
class UpdateApplyRequest:
    parent_pid: int
    source_directory: Path
    destination_directory: Path
    executable_name: str
    updater_directory: Path
    staging_directory: Path
    persistent_log_path: Path
    target_version: str

    @classmethod
    def load(cls, path: Path) -> "UpdateApplyRequest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(data.get("schema_version", 0)) != 1:
            raise RuntimeError("Unsupported updater request schema.")

        request = cls(
            parent_pid=int(data["parent_pid"]),
            source_directory=Path(data["source_directory"]).resolve(),
            destination_directory=Path(data["destination_directory"]).resolve(),
            executable_name=Path(str(data["executable_name"])).name,
            updater_directory=Path(data["updater_directory"]).resolve(),
            staging_directory=Path(data["staging_directory"]).resolve(),
            persistent_log_path=Path(data["persistent_log_path"]).resolve(),
            target_version=str(data["target_version"]),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if self.parent_pid <= 0:
            raise RuntimeError("Invalid launcher process id.")
        if not self.executable_name or self.executable_name in {".", ".."}:
            raise RuntimeError("Invalid launcher executable name.")
        if not self.source_directory.is_dir():
            raise FileNotFoundError(f"Prepared update directory does not exist: {self.source_directory}")
        if not self.destination_directory.is_dir():
            raise FileNotFoundError(f"Launcher directory does not exist: {self.destination_directory}")
        if not (self.source_directory / self.executable_name).is_file():
            raise RuntimeError(f"The update package does not contain {self.executable_name}.")
        if self.source_directory == self.destination_directory:
            raise RuntimeError("Update source and destination cannot be the same directory.")


class UpdateApplier:
    COPY_RETRIES = 30
    COPY_RETRY_DELAY_SECONDS = 0.25

    def __init__(self, request: UpdateApplyRequest) -> None:
        self.request = request
        self.backup_directory = request.updater_directory / "backup"
        self.temporary_log_path = request.updater_directory / "update.log"
        self.new_files: list[Path] = []

    def run(self) -> int:
        try:
            self._log(f"Updater process started for {self.request.target_version}")
            self._log(f"Waiting for launcher process {self.request.parent_pid}")
            self._wait_for_process_exit(self.request.parent_pid)
            time.sleep(0.6)

            self._backup_existing_files()
            self._copy_update_files()
            self._verify_updated_executable()
            self._start_launcher()
            self._log(f"Update to {self.request.target_version} completed")
            shutil.rmtree(self.request.staging_directory, ignore_errors=True)
            return 0
        except Exception as error:
            self._log(f"Update failed: {error}")
            try:
                self._restore_backup()
                self._log("Rollback completed")
            except Exception as rollback_error:
                self._log(f"Rollback failed: {rollback_error}")

            try:
                self._start_launcher()
                self._log("Previous launcher restarted after update failure")
            except Exception as restart_error:
                self._log(f"Could not restart the launcher after failure: {restart_error}")

            self._show_error(str(error))
            return 1

    def _backup_existing_files(self) -> None:
        self._log("Creating rollback backup")
        for source_path in self._iter_source_files():
            relative_path = source_path.relative_to(self.request.source_directory)
            destination_path = self.request.destination_directory / relative_path
            if destination_path.is_file():
                backup_path = self.backup_directory / relative_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination_path, backup_path)
            elif not destination_path.exists():
                self.new_files.append(destination_path)

    def _copy_update_files(self) -> None:
        self._log(f"Copying update from {self.request.source_directory} to {self.request.destination_directory}")
        for source_path in self._iter_source_files():
            relative_path = source_path.relative_to(self.request.source_directory)
            destination_path = self.request.destination_directory / relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            self._copy_with_retry(source_path, destination_path)

    def _restore_backup(self) -> None:
        self._log("Restoring files after update failure")
        for path in reversed(self.new_files):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        if not self.backup_directory.is_dir():
            return
        for backup_path in sorted((path for path in self.backup_directory.rglob("*") if path.is_file()), key=lambda path: len(path.parts)):
            relative_path = backup_path.relative_to(self.backup_directory)
            destination_path = self.request.destination_directory / relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            self._copy_with_retry(backup_path, destination_path)

    def _verify_updated_executable(self) -> None:
        updated_executable = self.request.destination_directory / self.request.executable_name
        source_executable = self.request.source_directory / self.request.executable_name
        if not updated_executable.is_file():
            raise RuntimeError(f"Updated executable was not found: {updated_executable}")
        if updated_executable.stat().st_size != source_executable.stat().st_size:
            raise RuntimeError("The updated executable size does not match the release package.")

    def _start_launcher(self) -> None:
        executable = self.request.destination_directory / self.request.executable_name
        if not executable.is_file():
            raise FileNotFoundError(f"Launcher executable does not exist: {executable}")

        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [str(executable), "--cleanup-update", str(self.request.updater_directory), str(os.getpid())],
            cwd=str(self.request.destination_directory),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creation_flags,
        )

    def _copy_with_retry(self, source: Path, destination: Path) -> None:
        last_error: OSError | None = None
        for attempt in range(self.COPY_RETRIES):
            try:
                shutil.copy2(source, destination)
                return
            except OSError as error:
                last_error = error
                if attempt + 1 < self.COPY_RETRIES:
                    time.sleep(self.COPY_RETRY_DELAY_SECONDS)
        raise RuntimeError(f"Could not replace {destination}: {last_error}") from last_error

    def _iter_source_files(self) -> list[Path]:
        return sorted((path for path in self.request.source_directory.rglob("*") if path.is_file()), key=lambda path: str(path).lower())

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        for path in (self.temporary_log_path, self.request.persistent_log_path):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as file:
                    file.write(line)
                    file.flush()
            except OSError:
                continue

    @staticmethod
    def _wait_for_process_exit(pid: int, timeout_seconds: float = 120.0) -> None:
        if os.name == "nt":
            synchronize = 0x00100000
            wait_timeout = 0x00000102
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(synchronize, False, pid)
            if not handle:
                return
            try:
                result = kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000))
                if result == wait_timeout:
                    raise TimeoutError("The launcher did not close within two minutes.")
            finally:
                kernel32.CloseHandle(handle)
            return

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.2)
        raise TimeoutError("The launcher did not close within two minutes.")

    def _show_error(self, message: str) -> None:
        if os.name != "nt":
            return
        text = (
            "MCW Launcher could not finish the update.\n\n"
            f"{message}\n\n"
            f"Log: {self.request.persistent_log_path}"
        )
        try:
            ctypes.windll.user32.MessageBoxW(None, text, "MCW Launcher Update", 0x10)
        except Exception:
            pass


def run_update_applier(request_path: Path) -> int:
    try:
        request = UpdateApplyRequest.load(Path(request_path))
    except Exception as error:
        if os.name == "nt":
            try:
                ctypes.windll.user32.MessageBoxW(None, f"Invalid MCW update request.\n\n{error}", "MCW Launcher Update", 0x10)
            except Exception:
                pass
        return 2
    return UpdateApplier(request).run()
