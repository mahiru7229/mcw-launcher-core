from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from src.core.fs.paths import Paths
from src.core.update.update_errors import AutomaticUpdateUnsupportedError
from src.models.update.update_info import PreparedUpdate


class _ShellUpdaterProcess:
    """Wrapper when process is launched via Windows ShellExecuteExW."""

    def __init__(self, handle: int | None = None) -> None:
        self._handle = handle

    def poll(self) -> int | None:
        if not self._handle:
            return None
        import ctypes
        from ctypes import wintypes

        code = wintypes.DWORD()
        if ctypes.windll.kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            if code.value == 259:  # STILL_ACTIVE
                return None
            return int(code.value)
        return None

    def terminate(self) -> None:
        if self._handle:
            import ctypes

            try:
                ctypes.windll.kernel32.TerminateProcess(self._handle, 1)
            except Exception:
                pass

    def wait(self, timeout: float = 0) -> int | None:
        if not self._handle:
            return None
        import ctypes

        timeout_ms = int(timeout * 1000) if timeout > 0 else 0xFFFFFFFF
        ctypes.windll.kernel32.WaitForSingleObject(self._handle, timeout_ms)
        return self.poll()

    def kill(self) -> None:
        self.terminate()

    def __del__(self) -> None:
        if getattr(self, "_handle", None):
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._handle)
            except Exception:
                pass


class WindowsUpdateInstaller:
    """Launch the updater binary bundled inside the incoming Windows package."""

    STARTUP_GRACE_SECONDS = 1.0
    READY_TIMEOUT_SECONDS = 5.0
    READY_POLL_SECONDS = 0.05
    PACKAGE_MANIFEST_NAME = "mcw-update.json"
    PACKAGE_MANIFEST_SCHEMA_VERSION = 2
    EXPECTED_UPDATER = PurePosixPath("updater/MCW Updater.exe")

    @staticmethod
    def is_supported() -> bool:
        return os.name == "nt" and bool(getattr(sys, "frozen", False))

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
                "Automatic installation is only available in the packaged Windows launcher."
            )

        executable = Path(executable_path) if executable_path is not None else Path(sys.executable)
        destination = Path(install_directory) if install_directory is not None else executable.resolve().parent
        source = prepared.content_directory.resolve()
        destination = destination.resolve()
        executable = executable.resolve()
        persistent_log = Path(persistent_log_path) if persistent_log_path is not None else Paths.updater_log_path()
        persistent_log = persistent_log.resolve()

        cls._validate_paths(source, destination, executable)
        incoming_updater = cls._bundled_updater(source)

        updater_directory = Path(tempfile.gettempdir()) / f"mcw-launcher-updater-{uuid.uuid4().hex}"
        updater_directory.mkdir(parents=True, exist_ok=False)
        updater_executable = updater_directory / "MCW Updater.exe"
        request_path = updater_directory / "update-request.json"
        ready_path = updater_directory / "updater-ready.json"

        try:
            # Critical v2 contract: execute updater code from the incoming release,
            # never a renamed/copy of the currently running launcher.
            shutil.copy2(incoming_updater, updater_executable)
            if os.name == "nt":
                try:
                    import ctypes
                    ctypes.windll.kernel32.DeleteFileW(f"{updater_executable}:Zone.Identifier")
                except Exception:
                    pass
            request = {
                "schema_version": 2,
                "parent_pid": int(parent_pid if parent_pid is not None else os.getpid()),
                "source_directory": str(source),
                "destination_directory": str(destination),
                "executable_name": executable.name,
                "updater_directory": str(updater_directory),
                "staging_directory": str(prepared.staging_directory.resolve()),
                "persistent_log_path": str(persistent_log),
                "target_version": str(prepared.info.version),
                "ready_path": str(ready_path),
            }
            request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
            process = cls._start_updater_process(updater_executable, request_path, destination)
            if cls._wait_for_ready(process, ready_path, cls.READY_TIMEOUT_SECONDS):
                return request_path

            exit_code = process.poll()
            if exit_code is not None:
                detail = cls._read_startup_error(updater_directory, persistent_log)
                raise RuntimeError(
                    f"The bundled updater exited before the launcher closed (code {exit_code}).{detail}"
                )
            cls._stop_process(process)
            installed_updater = destination.joinpath(*cls.EXPECTED_UPDATER.parts)
            if installed_updater.is_file():
                fallback_executable = updater_directory / "MCW Updater Fallback.exe"
                shutil.copy2(installed_updater, fallback_executable)
                ready_path.unlink(missing_ok=True)
                fallback = cls._start_updater_process(fallback_executable, request_path, destination)
                # Beta 3's installed updater predates the ready handshake. Accept
                # a living legacy helper after the normal startup grace period.
                time.sleep(cls.STARTUP_GRACE_SECONDS)
                if fallback.poll() is None:
                    return request_path
                detail = cls._read_startup_error(updater_directory, persistent_log)
                raise RuntimeError(f"Both incoming and installed fallback updaters failed to start.{detail}")

            detail = cls._read_startup_error(updater_directory, persistent_log)
            raise RuntimeError(f"The bundled updater did not signal ready and no installed fallback updater is available.{detail}")
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
    def _bundled_updater(cls, source: Path) -> Path:
        manifest_path = source / cls.PACKAGE_MANIFEST_NAME
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Could not read the bundled updater manifest: {error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("The update package manifest must be a JSON object.")
        if int(payload.get("schema_version", 0) or 0) != cls.PACKAGE_MANIFEST_SCHEMA_VERSION:
            raise RuntimeError("The update package does not use bundled-updater schema 2.")
        if str(payload.get("platform") or "").strip().casefold() != "windows-x64":
            raise RuntimeError("The update package does not target windows-x64.")
        raw = str(payload.get("updater") or "").replace("\\", "/").strip()
        path = PurePosixPath(raw)
        if path != cls.EXPECTED_UPDATER:
            raise RuntimeError(f"The update package must declare {cls.EXPECTED_UPDATER.as_posix()} as its updater.")
        updater = source.joinpath(*path.parts)
        if not updater.is_file():
            raise RuntimeError(f"The bundled updater is missing: {path.as_posix()}")
        return updater

    @classmethod
    def _start_updater_process(
        cls,
        updater_executable: Path,
        request_path: Path,
        destination: Path,
    ) -> subprocess.Popen | _ShellUpdaterProcess:
        command = [str(updater_executable), "--apply-update", str(request_path)]
        base_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
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
            except OSError as error:
                if getattr(error, "winerror", None) == 4551:
                    shell_proc = cls._start_windows_updater_shell(updater_executable, request_path, destination)
                    if shell_proc is not None:
                        return shell_proc
                    raise
        try:
            return subprocess.Popen(command, creationflags=base_flags, **kwargs)
        except OSError as error:
            if getattr(error, "winerror", None) == 4551:
                shell_proc = cls._start_windows_updater_shell(updater_executable, request_path, destination)
                if shell_proc is not None:
                    return shell_proc
            raise

    @classmethod
    def _start_windows_updater_shell(
        cls,
        updater_executable: Path,
        request_path: Path,
        destination: Path,
    ) -> _ShellUpdaterProcess | None:
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", wintypes.LPVOID),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("hIconOrMonitor", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE),
                ]

            SEE_MASK_NOCLOSEPROCESS = 0x00000040
            SW_SHOWNORMAL = 1
            info = SHELLEXECUTEINFOW()
            info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
            info.fMask = SEE_MASK_NOCLOSEPROCESS
            info.lpVerb = "open"
            info.lpFile = str(updater_executable)
            info.lpParameters = f'--apply-update "{request_path}"'
            info.lpDirectory = str(destination)
            info.nShow = SW_SHOWNORMAL

            shell32 = ctypes.windll.shell32
            ctypes.set_last_error(0)
            if shell32.ShellExecuteExW(ctypes.byref(info)):
                return _ShellUpdaterProcess(info.hProcess)
            return None
        except Exception:
            return None

    @classmethod
    def _wait_for_ready(cls, process: subprocess.Popen | _ShellUpdaterProcess, ready_path: Path, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() <= deadline:
            if ready_path.is_file():
                return True
            if process.poll() is not None:
                return False
            time.sleep(cls.READY_POLL_SECONDS)
        return ready_path.is_file()

    @staticmethod
    def _stop_process(process: subprocess.Popen | _ShellUpdaterProcess) -> None:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except Exception:
                    process.kill()
        except Exception:
            pass

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
