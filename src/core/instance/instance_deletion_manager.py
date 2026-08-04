from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import base64
import json
import os
import shutil
import stat
import subprocess
import time

from src.core.fs.paths import Paths
from src.core.instance.errors import InstanceDeletionError
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.runtime.game_runtime_manager import GameRuntimeManager
from src.models.instance.instance import Instance


@dataclass(frozen=True, slots=True)
class InstanceLockingProcess:
    pid: int
    name: str = ""
    command_line: str = ""


class InstanceDeletionManager:
    """Delete one instance without leaving a partially removed registry entry."""

    MAX_ATTEMPTS = 7
    BACKOFF_SECONDS = (0.10, 0.20, 0.35, 0.55, 0.80, 1.10, 1.40)
    JAVA_PROCESS_NAMES = {"java.exe", "javaw.exe", "java", "javaw"}
    PENDING_SCHEMA_VERSION = 1

    @classmethod
    def delete(cls, instance: Instance) -> bool:
        target = cls._safe_instance_dir(instance)
        if not target.exists():
            InstanceRunLock.remove_for(instance, force=True)
            return True

        cls._stop_normal_runtime(instance)
        success, last_error, locked_path, locking_processes = cls._delete_target(target)
        if success:
            InstanceRunLock.remove_for(instance, force=True)
            return True

        cls.schedule(instance, locked_path)
        raise InstanceDeletionError(
            instance_name=instance.name,
            instance_dir=target,
            locked_path=locked_path,
            attempts=cls.MAX_ATTEMPTS,
            processes=tuple((item.pid, item.name, item.command_line) for item in locking_processes),
            winerror=getattr(last_error, "winerror", None),
            scheduled=True,
        ) from last_error

    @classmethod
    def process_pending(cls) -> tuple[str, ...]:
        payload = cls._load_pending_payload()
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list) or not entries:
            return ()

        deleted_names: list[str] = []
        remaining: list[dict] = []
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            name = str(raw_entry.get("name") or "").strip()
            raw_path = str(raw_entry.get("instance_dir") or "").strip()
            try:
                target = cls._safe_pending_target(Path(raw_path))
            except (OSError, RuntimeError, ValueError):
                continue
            if not target.exists():
                if name:
                    deleted_names.append(name)
                continue
            success, _error, locked_path, processes = cls._delete_target(target)
            if success:
                if name:
                    deleted_names.append(name)
                continue
            entry = dict(raw_entry)
            entry["last_locked_path"] = str(locked_path or target)
            entry["last_processes"] = [
                {"pid": process.pid, "name": process.name, "command_line": process.command_line}
                for process in processes
            ]
            remaining.append(entry)

        cls._save_pending_entries(remaining)
        return tuple(dict.fromkeys(deleted_names))

    @classmethod
    def schedule(cls, instance: Instance, locked_path: Path | None = None) -> None:
        target = cls._safe_instance_dir(instance)
        payload = cls._load_pending_payload()
        entries = payload.get("entries") if isinstance(payload, dict) else None
        normalized_entries = [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
        identity = str(target.resolve(strict=False)).casefold()
        normalized_entries = [
            item for item in normalized_entries
            if str(item.get("instance_dir") or "").strip().casefold() != identity
        ]
        normalized_entries.append({
            "instance_id": str(getattr(instance, "instance_id", "") or ""),
            "name": instance.name,
            "instance_dir": str(target),
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "last_locked_path": str(locked_path or ""),
        })
        cls._save_pending_entries(normalized_entries)

    @classmethod
    def _delete_target(cls, target: Path) -> tuple[bool, OSError | None, Path | None, tuple[InstanceLockingProcess, ...]]:
        last_error: OSError | None = None
        locked_path: Path | None = None
        locking_processes: tuple[InstanceLockingProcess, ...] = ()
        for attempt in range(1, cls.MAX_ATTEMPTS + 1):
            try:
                shutil.rmtree(target, onerror=cls._remove_readonly)
                return True, None, None, locking_processes
            except OSError as error:
                last_error = error
                locked_path = cls._locked_path(error, target)
                discovered = cls._find_relevant_processes(target)
                if discovered:
                    locking_processes = discovered
                    cls._terminate_processes(discovered)
                if attempt < cls.MAX_ATTEMPTS:
                    time.sleep(cls.BACKOFF_SECONDS[min(attempt - 1, len(cls.BACKOFF_SECONDS) - 1)])
        return False, last_error, locked_path, locking_processes

    @classmethod
    def _safe_instance_dir(cls, instance: Instance) -> Path:
        return cls._safe_pending_target(Path(instance.instance_dir))

    @classmethod
    def _safe_pending_target(cls, candidate: Path) -> Path:
        root = Paths.instances_root().resolve(strict=False)
        target = Path(candidate).resolve(strict=False)
        try:
            relative = target.relative_to(root)
        except ValueError as error:
            raise RuntimeError(f"Refusing to delete an instance outside the configured instance root: {target}") from error
        if len(relative.parts) != 1 or relative.name.casefold() in {".runtime", "instances.json"}:
            raise RuntimeError(f"Refusing to delete an unsafe instance path: {target}")
        return target

    @classmethod
    def _stop_normal_runtime(cls, instance: Instance) -> None:
        GameRuntimeManager.stop(instance, graceful_timeout=2.5)
        active = InstanceRunLock.active_for(instance)
        if active is None:
            return
        if active.state == "preparing" and active.launcher_pid == os.getpid():
            raise InstanceDeletionError(
                instance_name=instance.name,
                instance_dir=Path(instance.instance_dir),
                locked_path=None,
                attempts=0,
                processes=((active.launcher_pid, "MCW Launcher", "launch preparation"),),
                detail="The instance is still being prepared. Cancel the launch task before deleting it.",
            )
        if active.minecraft_pid is not None:
            cls._terminate_pid(active.minecraft_pid, force=False)
            cls._wait_for_exit(active.minecraft_pid, 1.5)
            if cls._pid_alive(active.minecraft_pid):
                cls._terminate_pid(active.minecraft_pid, force=True)
                cls._wait_for_exit(active.minecraft_pid, 2.0)

    @staticmethod
    def _remove_readonly(function, path: str, _exc_info) -> None:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        function(path)

    @staticmethod
    def _locked_path(error: OSError, fallback: Path) -> Path:
        filename = getattr(error, "filename", None)
        return Path(filename) if filename else fallback

    @classmethod
    def _find_relevant_processes(cls, instance_dir: Path) -> tuple[InstanceLockingProcess, ...]:
        if os.name != "nt":
            return ()
        needle = str(instance_dir.resolve(strict=False))
        escaped = needle.replace("'", "''")
        script = (
            f"$needle = '{escaped}'; "
            "$items = Get-CimInstance Win32_Process | Where-Object { "
            "$_.ProcessId -ne $PID -and $_.CommandLine -and "
            "$_.CommandLine.IndexOf($needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and "
            "$_.Name -match '^javaw?\\.exe$' }; "
            "$items | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ()
        if completed.returncode != 0 or not completed.stdout.strip():
            return ()
        try:
            payload = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError, ValueError):
            return ()
        rows = payload if isinstance(payload, list) else [payload]
        processes: list[InstanceLockingProcess] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                pid = int(row.get("ProcessId") or 0)
            except (TypeError, ValueError):
                continue
            name = str(row.get("Name") or "").strip()
            command_line = str(row.get("CommandLine") or "").strip()
            if pid <= 0 or pid == os.getpid() or name.casefold() not in cls.JAVA_PROCESS_NAMES:
                continue
            processes.append(InstanceLockingProcess(pid=pid, name=name, command_line=command_line))
        return tuple(processes)

    @classmethod
    def _terminate_processes(cls, processes: tuple[InstanceLockingProcess, ...]) -> None:
        for process in processes:
            cls._terminate_pid(process.pid, force=False)
        for process in processes:
            cls._wait_for_exit(process.pid, 0.75)
            if cls._pid_alive(process.pid):
                cls._terminate_pid(process.pid, force=True)

    @staticmethod
    def _terminate_pid(pid: int, force: bool) -> None:
        if pid <= 0 or pid == os.getpid():
            return
        if os.name == "nt":
            command = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                command.append("/F")
            try:
                subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            return
        try:
            os.kill(pid, 9 if force else 15)
        except OSError:
            pass

    @staticmethod
    def _wait_for_exit(pid: int, timeout: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout)
        while time.monotonic() < deadline:
            if not InstanceDeletionManager._pid_alive(pid):
                return
            time.sleep(0.05)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        return InstanceRunLock._is_process_alive(pid)

    @classmethod
    def _pending_path(cls) -> Path:
        directory = Paths.instances_root() / ".runtime"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "pending-instance-deletions.json"

    @classmethod
    def _load_pending_payload(cls) -> dict:
        path = cls._pending_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, json.JSONDecodeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    @classmethod
    def _save_pending_entries(cls, entries: list[dict]) -> None:
        path = cls._pending_path()
        if not entries:
            path.unlink(missing_ok=True)
            return
        payload = {"schema_version": cls.PENDING_SCHEMA_VERSION, "entries": entries}
        temporary = path.with_name(f"{path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
