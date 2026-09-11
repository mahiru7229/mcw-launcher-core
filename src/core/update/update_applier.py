from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ctypes
import filecmp
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
import uuid

from src.core.system.platform_info import PlatformInfo


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
        if int(data.get("schema_version", 0)) != 2:
            raise RuntimeError("Unsupported updater request schema. MCW Updater v2 requires schema 2.")

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
    EXECUTABLE_REPLACE_RETRIES = 240
    COPY_RETRY_DELAY_SECONDS = 0.25
    WINDOWS_RELEASE_TIMEOUT_SECONDS = 60.0
    WINDOWS_RELEASE_POLL_SECONDS = 0.20
    WINDOWS_SETTLE_SECONDS = 0.75
    WINDOWS_RETRIABLE_REPLACE_ERRORS = frozenset({5, 32, 33})  # ACCESS_DENIED / SHARING_VIOLATION / LOCK_VIOLATION

    def __init__(self, request: UpdateApplyRequest) -> None:
        self.request = request
        self.backup_directory = request.updater_directory / "backup"
        self.temporary_log_path = request.updater_directory / "update.log"
        self.new_files: list[Path] = []
        self.stale_files = self._stale_managed_files()
        self.cleanup_paths = self._cleanup_paths(self.request.source_directory)

    def run(self) -> int:
        try:
            self._log(f"Updater process started for {self.request.target_version}")
            self._log(f"Waiting for launcher process {self.request.parent_pid}")
            self._wait_for_process_exit(self.request.parent_pid)
            self._log("Primary launcher process exited")
            self._wait_for_launcher_release()

            self._backup_existing_files()
            self._copy_update_files()
            self._remove_stale_files()
            self._remove_cleanup_paths()
            self._verify_updated_executable()
            self._start_launcher()
            self._log(f"Update to {self.request.target_version} completed")
            shutil.rmtree(self.request.staging_directory, ignore_errors=True)
            return 0
        except Exception as error:
            self._log(f"Update failed: {error}")
            rollback_completed = False
            try:
                self._restore_backup()
                rollback_completed = True
                self._log("Rollback completed")
            except Exception as rollback_error:
                self._log(f"Rollback failed: {rollback_error}")

            if rollback_completed:
                try:
                    self._start_launcher(restored=True)
                    self._log("Previous launcher restarted after update failure")
                except Exception as restart_error:
                    self._log(f"Could not restart the launcher after failure: {restart_error}")
            else:
                self._log("Launcher was not restarted because rollback did not complete safely")

            self._show_error(str(error), rollback_completed=rollback_completed)
            return 1

    def _backup_existing_files(self) -> None:
        self._log("Creating rollback backup")
        source_relative = {path.relative_to(self.request.source_directory) for path in self._iter_source_files()}
        for relative_path in sorted(source_relative | set(self.stale_files), key=lambda path: str(path).casefold()):
            destination_path = self.request.destination_directory / relative_path
            if destination_path.is_file():
                backup_path = self.backup_directory / relative_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination_path, backup_path)
            elif relative_path in source_relative and not destination_path.exists():
                self.new_files.append(destination_path)

        # cleanup_paths may intentionally remove content that was never part of
        # a previous managed-file manifest (for example old bundled docs). Keep
        # a recovery copy so a failed transaction can restore it.
        for relative_path in self.cleanup_paths:
            target = self.request.destination_directory / relative_path
            if target.is_symlink():
                raise RuntimeError(f"Refusing to clean symbolic-link path: {target}")
            if target.is_file():
                backup = self.backup_directory / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            elif target.is_dir():
                for file_path in target.rglob("*"):
                    if file_path.is_symlink():
                        raise RuntimeError(f"Refusing to clean directory containing a symbolic link: {file_path}")
                    if not file_path.is_file():
                        continue
                    child_relative = file_path.relative_to(self.request.destination_directory)
                    backup = self.backup_directory / child_relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, backup)

    def _copy_update_files(self) -> None:
        self._log(f"Copying update from {self.request.source_directory} to {self.request.destination_directory}")
        source_files = self._iter_source_files()
        source_executable = self.request.source_directory / self.request.executable_name
        destination_executable = self.request.destination_directory / self.request.executable_name

        # Replace the launcher executable before mutating the rest of the installation.
        # A PyInstaller/AV file lock can linger briefly after the launcher process exits;
        # failing here first avoids leaving a mixed-version installation behind.
        self._log("Replacing launcher executable before the remaining update files")
        self._copy_with_retry(source_executable, destination_executable)

        for source_path in source_files:
            if source_path == source_executable:
                continue
            relative_path = source_path.relative_to(self.request.source_directory)
            destination_path = self.request.destination_directory / relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            self._copy_with_retry(source_path, destination_path)

    def _remove_stale_files(self) -> None:
        for relative_path in self.stale_files:
            target = self.request.destination_directory / relative_path
            try:
                target.unlink(missing_ok=True)
            except OSError as error:
                raise RuntimeError(f"Could not remove obsolete launcher file {target}: {error}") from error


    def _remove_cleanup_paths(self) -> None:
        for relative_path in self.cleanup_paths:
            target = self.request.destination_directory / relative_path
            if not target.exists() and not target.is_symlink():
                continue
            self._log(f"Cleaning obsolete launcher path: {relative_path.as_posix()}")
            try:
                if target.is_symlink() or target.is_file():
                    target.unlink(missing_ok=True)
                elif target.is_dir():
                    shutil.rmtree(target)
            except OSError as error:
                raise RuntimeError(f"Could not clean obsolete launcher path {target}: {error}") from error

    @staticmethod
    def _cleanup_paths(root: Path) -> list[Path]:
        manifest_path = Path(root) / "mcw-update.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return []
        values = payload.get("cleanup_paths") if isinstance(payload, dict) else None
        if values is None:
            return []
        if not isinstance(values, list):
            raise RuntimeError("The update package cleanup_paths value must be a list.")
        result: list[Path] = []
        seen: set[str] = set()
        for raw in values:
            normalized = str(raw or "").replace("\\", "/").strip().strip("/")
            path = PurePosixPath(normalized)
            if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise RuntimeError(f"Invalid cleanup path in update manifest: {raw}")
            if ":" in path.parts[0]:
                raise RuntimeError(f"Invalid cleanup path in update manifest: {raw}")
            key = path.as_posix().casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(Path(*path.parts))
        return sorted(result, key=lambda value: value.as_posix().casefold())

    def _stale_managed_files(self) -> list[Path]:
        previous = self._managed_files(self.request.destination_directory)
        incoming = self._managed_files(self.request.source_directory)
        if not previous or not incoming:
            return []
        return sorted((Path(*path.parts) for path in previous.difference(incoming)), key=lambda path: str(path).casefold())

    @staticmethod
    def _managed_files(root: Path) -> set[PurePosixPath]:
        manifest_path = Path(root) / "mcw-update.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return set()
        values = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            return set()
        managed: set[PurePosixPath] = set()
        for raw in values:
            normalized = str(raw or "").replace("\\", "/").strip()
            path = PurePosixPath(normalized)
            if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                return set()
            if not path.parts or ":" in path.parts[0]:
                return set()
            managed.add(path)
        return managed

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
            if self._files_equal(backup_path, destination_path):
                continue
            self._copy_with_retry(backup_path, destination_path)

    def _verify_updated_executable(self) -> None:
        updated_executable = self.request.destination_directory / self.request.executable_name
        source_executable = self.request.source_directory / self.request.executable_name
        if not updated_executable.is_file():
            raise RuntimeError(f"Updated executable was not found: {updated_executable}")
        if updated_executable.stat().st_size != source_executable.stat().st_size:
            raise RuntimeError("The updated executable size does not match the release package.")
        if not self.request.executable_name.casefold().endswith(".exe") and updated_executable.stat().st_mode & 0o111 == 0:
            raise RuntimeError("The updated Linux launcher is not executable.")

    def _start_launcher(self, *, restored: bool = False) -> None:
        executable = self.request.destination_directory / self.request.executable_name
        if not executable.is_file():
            raise FileNotFoundError(f"Launcher executable does not exist: {executable}")

        kwargs = {
            "cwd": str(self.request.destination_directory),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if PlatformInfo.current().os_name == "windows":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        self._log("Starting restored launcher after rollback" if restored else "Starting updated launcher")
        subprocess.Popen(
            [str(executable), "--cleanup-update", str(self.request.updater_directory), str(os.getpid())],
            **kwargs,
        )

    def _copy_with_retry(self, source: Path, destination: Path) -> None:
        if self._is_launcher_executable(destination) and PlatformInfo.current().os_name == "windows":
            self._copy_windows_launcher_with_retry(source, destination)
            return

        retries = self._replace_retries_for(destination)
        temporary = destination.with_name(f".{destination.name}.mcw-update-{uuid.uuid4().hex}.tmp")
        last_error: OSError | None = None

        try:
            shutil.copy2(source, temporary)
            for attempt in range(retries):
                try:
                    os.replace(temporary, destination)
                    return
                except OSError as error:
                    last_error = error
                    if attempt + 1 < retries:
                        time.sleep(self.COPY_RETRY_DELAY_SECONDS)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

        raise RuntimeError(f"Could not replace {destination}: {last_error}") from last_error

    def _copy_windows_launcher_with_retry(self, source: Path, destination: Path) -> None:
        """Replace the Windows launcher using native semantics with a rename-away fallback.

        A mapped PE image can outlive the GUI PID and still reject replace/delete even when a
        DELETE-access CreateFile probe succeeds.  The real ReplaceFileW / MoveFileExW operation is
        therefore the source of truth.  If replacing the existing pathname is blocked but Windows
        permits renaming the old image, move it into the updater directory first and then install
        the new image at the original pathname.  This mirrors robust native self-updaters and avoids
        starting a mixed-version transaction when the executable cannot actually be transitioned.
        """
        temporary = destination.with_name(f".{destination.name}.mcw-update-{uuid.uuid4().hex}.tmp")
        retired_directory = self.request.updater_directory / "retired"
        retired_directory.mkdir(parents=True, exist_ok=True)
        retired = retired_directory / f"{destination.name}.{uuid.uuid4().hex}.old"
        original_attributes = self._windows_file_attributes(destination)
        changed_readonly = False
        last_detail = "unknown Windows replacement error"

        try:
            shutil.copy2(source, temporary)
            if original_attributes is not None and original_attributes & 0x1:
                if self._windows_set_file_attributes(destination, original_attributes & ~0x1):
                    changed_readonly = True
                    self._log("Cleared READONLY attribute from the installed launcher before replacement")
                else:
                    code = self._windows_last_error()
                    self._log(f"Could not clear launcher READONLY attribute: {self._format_windows_error(code)}")

            for attempt in range(self.EXECUTABLE_REPLACE_RETRIES):
                direct_ok, direct_api, direct_error = self._windows_replace_existing(temporary, destination)
                if direct_ok:
                    if attempt:
                        self._log(f"Launcher executable became replaceable after {attempt + 1} attempts")
                    self._log(f"Launcher executable replaced successfully using {direct_api}")
                    return

                last_detail = f"{direct_api}: {self._format_windows_error(direct_error)}"
                if attempt == 0:
                    self._log(f"Direct launcher replacement blocked ({last_detail})")

                # ERROR_ACCESS_DENIED / SHARING_VIOLATION / LOCK_VIOLATION are exactly the cases
                # where rename-away can free the public pathname while an old image section drains.
                if direct_error in self.WINDOWS_RETRIABLE_REPLACE_ERRORS and destination.exists():
                    renamed, rename_error = self._windows_move_file(destination, retired, replace_existing=False)
                    if renamed:
                        self._log("Direct replacement is blocked; using Windows rename-away fallback")
                        installed, install_error = self._windows_move_file(temporary, destination, replace_existing=False)
                        if installed:
                            self._log("Launcher executable installed successfully after rename-away fallback")
                            self._cleanup_retired_windows_executable(retired)
                            return

                        # The old launcher pathname must be restored immediately if installing the
                        # new file fails.  Do not continue with the rest of the update in this state.
                        restored, restore_error = self._windows_move_file(retired, destination, replace_existing=False)
                        if not restored:
                            raise RuntimeError(
                                "Windows rename-away fallback could not restore the previous launcher after "
                                f"the new launcher install failed. install={self._format_windows_error(install_error)}; "
                                f"restore={self._format_windows_error(restore_error)}"
                            )
                        last_detail = f"MoveFileExW(new launcher): {self._format_windows_error(install_error)}"
                    else:
                        last_detail = f"MoveFileExW(rename old launcher): {self._format_windows_error(rename_error)}"

                if attempt + 1 < self.EXECUTABLE_REPLACE_RETRIES:
                    if attempt == 0:
                        max_wait = self.EXECUTABLE_REPLACE_RETRIES * self.COPY_RETRY_DELAY_SECONDS
                        self._log(f"Launcher transition is still blocked; retrying for up to {max_wait:.0f} seconds")
                    time.sleep(self.COPY_RETRY_DELAY_SECONDS)
        finally:
            # If replacement never succeeded, preserve the previous readonly state.
            if changed_readonly and destination.exists() and temporary.exists() and original_attributes is not None:
                self._windows_set_file_attributes(destination, original_attributes)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

        raise RuntimeError(f"Could not transition Windows launcher executable {destination}: {last_detail}")

    def _replace_retries_for(self, destination: Path) -> int:
        if self._is_launcher_executable(destination):
            return self.EXECUTABLE_REPLACE_RETRIES
        return self.COPY_RETRIES

    def _is_launcher_executable(self, path: Path) -> bool:
        return path.name.casefold() == self.request.executable_name.casefold()

    @staticmethod
    def _files_equal(first: Path, second: Path) -> bool:
        if not first.is_file() or not second.is_file():
            return False
        try:
            return filecmp.cmp(first, second, shallow=False)
        except OSError:
            return False

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
        if PlatformInfo.current().os_name == "windows":
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

    def _wait_for_launcher_release(self, timeout_seconds: float | None = None) -> None:
        """Wait for processes using this installation's launcher path to exit.

        Beta 5 treated a successful CreateFile(DELETE) probe as proof that the executable could be
        replaced.  Live logs demonstrated that Windows can still reject rename/replace afterward
        (for example while a mapped image section drains).  Beta 6 deliberately avoids claiming the
        file is unlocked here.  The definitive gate is the native replacement transaction itself.
        """
        if PlatformInfo.current().os_name != "windows":
            return

        executable = (self.request.destination_directory / self.request.executable_name).resolve()
        timeout = self.WINDOWS_RELEASE_TIMEOUT_SECONDS if timeout_seconds is None else max(0.0, timeout_seconds)
        deadline = time.monotonic() + timeout
        previous_pids: tuple[int, ...] | None = None

        while True:
            pids = tuple(self._matching_windows_processes(executable))
            if not pids:
                if self.WINDOWS_SETTLE_SECONDS > 0:
                    time.sleep(self.WINDOWS_SETTLE_SECONDS)
                # Re-scan after a short settle window in case a PyInstaller sibling was still exiting.
                pids = tuple(self._matching_windows_processes(executable))
                if not pids:
                    self._log("No launcher process remains; Windows replacement transaction may begin")
                    return

            if pids != previous_pids:
                previous_pids = pids
                self._log(
                    "Detected remaining launcher process(es) for this installation: "
                    + ", ".join(str(pid) for pid in pids)
                )

            if time.monotonic() >= deadline:
                detail = f" process(es): {', '.join(str(pid) for pid in pids)}" if pids else ""
                raise TimeoutError(
                    f"{self.request.executable_name} is still running after {timeout:.0f} seconds;"
                    f" update was not started.{detail}"
                )
            time.sleep(self.WINDOWS_RELEASE_POLL_SECONDS)

    @staticmethod
    def _normalize_windows_path(path: Path | str) -> str:
        value = os.path.normcase(os.path.normpath(str(path)))
        if value.startswith("\\\\?\\"):
            value = value[4:]
        return value.rstrip("\\/")

    @classmethod
    def _matching_windows_processes(cls, executable: Path) -> list[int]:
        """Return processes whose full image path is exactly the target launcher path.

        Processes that cannot be queried are ignored here; the native replacement transaction is
        still authoritative and will abort safely if an unqueryable process or filter blocks it.
        """
        if os.name != "nt":
            return []

        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        kernel32 = ctypes.windll.kernel32

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            return []

        wanted = cls._normalize_windows_path(executable)
        own_pid = os.getpid()
        matches: list[int] = []
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        try:
            has_entry = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
            while has_entry:
                pid = int(entry.th32ProcessID)
                if pid > 0 and pid != own_pid:
                    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if handle:
                        try:
                            size = wintypes.DWORD(32768)
                            buffer = ctypes.create_unicode_buffer(size.value)
                            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                                if cls._normalize_windows_path(buffer.value) == wanted:
                                    matches.append(pid)
                        finally:
                            kernel32.CloseHandle(handle)
                has_entry = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
        finally:
            kernel32.CloseHandle(snapshot)
        return sorted(set(matches))

    @staticmethod
    def _windows_kernel32():
        return ctypes.WinDLL("kernel32", use_last_error=True)

    @staticmethod
    def _windows_last_error() -> int:
        try:
            return int(ctypes.get_last_error())
        except Exception:
            return 0

    @staticmethod
    def _format_windows_error(code: int) -> str:
        code = int(code or 0)
        try:
            detail = ctypes.FormatError(code).strip()
        except Exception:
            detail = ""
        return f"Win32 error {code}" + (f" ({detail})" if detail else "")

    @classmethod
    def _windows_file_attributes(cls, path: Path) -> int | None:
        if os.name != "nt" or not path.exists():
            return None
        from ctypes import wintypes
        kernel32 = cls._windows_kernel32()
        kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetFileAttributesW.restype = wintypes.DWORD
        invalid = 0xFFFFFFFF
        value = int(kernel32.GetFileAttributesW(str(path)))
        return None if value == invalid else value

    @classmethod
    def _windows_set_file_attributes(cls, path: Path, attributes: int) -> bool:
        if os.name != "nt":
            return False
        from ctypes import wintypes
        kernel32 = cls._windows_kernel32()
        kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        kernel32.SetFileAttributesW.restype = wintypes.BOOL
        return bool(kernel32.SetFileAttributesW(str(path), int(attributes)))

    @classmethod
    def _windows_replace_existing(cls, replacement: Path, destination: Path) -> tuple[bool, str, int]:
        """Try native replacement without modifying the old pathname on failure."""
        if os.name != "nt":
            raise RuntimeError("Windows replacement helper called on a non-Windows host.")
        from ctypes import wintypes
        kernel32 = cls._windows_kernel32()

        if destination.exists():
            REPLACEFILE_WRITE_THROUGH = 0x00000001
            REPLACEFILE_IGNORE_MERGE_ERRORS = 0x00000002
            kernel32.ReplaceFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID,
            ]
            kernel32.ReplaceFileW.restype = wintypes.BOOL
            ctypes.set_last_error(0)
            if kernel32.ReplaceFileW(
                str(destination), str(replacement), None,
                REPLACEFILE_WRITE_THROUGH | REPLACEFILE_IGNORE_MERGE_ERRORS,
                None, None,
            ):
                return True, "ReplaceFileW", 0
            replace_error = cls._windows_last_error()
        else:
            replace_error = 2

        MOVEFILE_REPLACE_EXISTING = 0x00000001
        MOVEFILE_WRITE_THROUGH = 0x00000008
        kernel32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        kernel32.MoveFileExW.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        if kernel32.MoveFileExW(
            str(replacement), str(destination), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        ):
            return True, "MoveFileExW(REPLACE_EXISTING)", 0
        move_error = cls._windows_last_error()
        # Prefer the MoveFileEx error because it is the last operation and directly mirrors os.replace.
        return False, "MoveFileExW(REPLACE_EXISTING)", int(move_error or replace_error)

    @classmethod
    def _windows_move_file(cls, source: Path, destination: Path, *, replace_existing: bool) -> tuple[bool, int]:
        if os.name != "nt":
            raise RuntimeError("Windows move helper called on a non-Windows host.")
        from ctypes import wintypes
        kernel32 = cls._windows_kernel32()
        MOVEFILE_REPLACE_EXISTING = 0x00000001
        MOVEFILE_WRITE_THROUGH = 0x00000008
        flags = MOVEFILE_WRITE_THROUGH | (MOVEFILE_REPLACE_EXISTING if replace_existing else 0)
        kernel32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        kernel32.MoveFileExW.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        if kernel32.MoveFileExW(str(source), str(destination), flags):
            return True, 0
        return False, cls._windows_last_error()

    def _cleanup_retired_windows_executable(self, retired: Path) -> None:
        try:
            retired.unlink(missing_ok=True)
            return
        except OSError as error:
            self._log(f"Retired launcher is still referenced; deferring cleanup: {error}")

        if os.name != "nt" or not retired.exists():
            return
        try:
            from ctypes import wintypes
            kernel32 = self._windows_kernel32()
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004
            kernel32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
            kernel32.MoveFileExW.restype = wintypes.BOOL
            ctypes.set_last_error(0)
            if kernel32.MoveFileExW(str(retired), None, MOVEFILE_DELAY_UNTIL_REBOOT):
                self._log("Retired launcher cleanup scheduled for the next Windows restart")
            else:
                self._log(
                    "Could not schedule retired launcher cleanup: "
                    + self._format_windows_error(self._windows_last_error())
                )
        except Exception as error:
            self._log(f"Could not schedule retired launcher cleanup: {error}")

    def _show_error(self, message: str, *, rollback_completed: bool = True) -> None:
        if os.name != "nt":
            return
        recovery_note = ""
        if not rollback_completed:
            recovery_note = (
                "\n\nRollback also failed, so MCW Launcher was not restarted. "
                "Keep the updater log and reinstall/reapply the current release before launching again."
            )
        text = (
            "MCW Launcher could not finish the update.\n\n"
            f"{message}"
            f"{recovery_note}\n\n"
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
