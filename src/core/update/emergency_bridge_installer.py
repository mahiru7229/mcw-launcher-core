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


class _ShellBridgeProcess:
    """Wrapper when bridge process is launched via Windows ShellExecuteExW."""

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

    @classmethod
    def _start(cls, helper: Path, destination: Path, tag_name: str) -> subprocess.Popen | _ShellBridgeProcess:
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
        try:
            return subprocess.Popen(command, **kwargs)
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 4551:
                proc = cls._start_windows_bridge_shell(helper, destination, tag_name)
                if proc is not None:
                    return proc
            raise

    @classmethod
    def _start_windows_bridge_shell(
        cls,
        helper: Path,
        destination: Path,
        tag_name: str,
    ) -> _ShellBridgeProcess | None:
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
            info.lpFile = str(helper)
            info.lpParameters = f'--install-dir "{destination}" --tag "{tag_name}" --force-close --cli'
            info.lpDirectory = str(destination)
            info.nShow = SW_SHOWNORMAL

            shell32 = ctypes.windll.shell32
            ctypes.set_last_error(0)
            if shell32.ShellExecuteExW(ctypes.byref(info)):
                return _ShellBridgeProcess(info.hProcess)
            return None
        except Exception:
            return None
