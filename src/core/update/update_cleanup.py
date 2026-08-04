from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time


CLEANUP_ARGUMENT = "--cleanup-update"
UPDATER_DIRECTORY_PREFIX = "mcw-launcher-updater-"


@dataclass(frozen=True, slots=True)
class UpdateCleanupRequest:
    updater_directory: Path
    updater_pid: int

    def validate(self) -> None:
        if self.updater_pid <= 0:
            raise RuntimeError("Invalid updater process id.")

        updater_directory = self.updater_directory.resolve()
        temporary_directory = Path(tempfile.gettempdir()).resolve()
        if updater_directory.parent != temporary_directory:
            raise RuntimeError("Updater cleanup directory must be inside the system temporary directory.")
        if not updater_directory.name.startswith(UPDATER_DIRECTORY_PREFIX):
            raise RuntimeError("Invalid updater cleanup directory name.")


class UpdateCleanupWorker:
    DELETE_RETRIES = 40
    DELETE_RETRY_DELAY_SECONDS = 0.25

    def __init__(self, request: UpdateCleanupRequest) -> None:
        request.validate()
        self.request = request

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="MCWUpdateCleanup", daemon=True)
        thread.start()
        return thread

    def run(self) -> None:
        self._wait_for_process_exit(self.request.updater_pid)
        for attempt in range(self.DELETE_RETRIES):
            try:
                shutil.rmtree(self.request.updater_directory)
                return
            except FileNotFoundError:
                return
            except OSError:
                if attempt + 1 < self.DELETE_RETRIES:
                    time.sleep(self.DELETE_RETRY_DELAY_SECONDS)

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
                    return
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


def consume_update_cleanup_arguments(arguments: list[str]) -> tuple[list[str], UpdateCleanupRequest | None]:
    try:
        index = arguments.index(CLEANUP_ARGUMENT)
    except ValueError:
        return list(arguments), None

    if len(arguments) <= index + 2:
        raise RuntimeError("Incomplete updater cleanup arguments.")

    request = UpdateCleanupRequest(updater_directory=Path(arguments[index + 1]), updater_pid=int(arguments[index + 2]))
    request.validate()
    cleaned_arguments = list(arguments[:index]) + list(arguments[index + 3:])
    return cleaned_arguments, request
