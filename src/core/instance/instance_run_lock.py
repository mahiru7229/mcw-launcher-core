from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.fs.paths import Paths
from src.core.instance.errors import InstanceAlreadyRunningError
from src.models.instance.instance import Instance


@dataclass(frozen=True, slots=True)
class RunningInstanceInfo:
    instance_id: str | None
    name: str
    state: str
    launcher_pid: int | None
    minecraft_pid: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class _LockSnapshot:
    payload: dict[str, Any] | None
    identity: tuple[int, int, int, int]
    age_seconds: float


@dataclass(slots=True)
class InstanceRunLock:
    instance_name: str
    lock_path: Path
    token: str

    LOCK_FILENAME = ".mcw-launcher.lock"
    SCHEMA_VERSION = 1
    MALFORMED_LOCK_GRACE_SECONDS = 5.0
    ACQUIRE_ATTEMPTS = 5

    @classmethod
    def acquire(cls, instance: Instance) -> InstanceRunLock:
        lock_path = cls.lock_path_for(instance)
        token = uuid.uuid4().hex
        payload = cls._build_payload(instance=instance, token=token, state="preparing", minecraft_pid=None)

        for _ in range(cls.ACQUIRE_ATTEMPTS):
            try:
                cls._create_lock_file(lock_path, payload)
                return cls(instance_name=instance.name, lock_path=lock_path, token=token)
            except FileExistsError:
                snapshot = cls._read_snapshot(lock_path)

                if snapshot is None:
                    continue

                if cls._snapshot_is_active(snapshot):
                    raise InstanceAlreadyRunningError(instance.name)

                cls._remove_if_unchanged(lock_path, snapshot)

        raise InstanceAlreadyRunningError(instance.name)

    def track_process(self, process: Any) -> bool:
        process_pid = getattr(process, "pid", None)
        wait = getattr(process, "wait", None)

        if not isinstance(process_pid, int) or process_pid <= 0 or not callable(wait):
            self.release()
            return False

        self._update_owned_lock(state="running", minecraft_pid=process_pid)

        watcher = threading.Thread(target=self._wait_and_release, args=(process,), name=f"instance-lock-{self.instance_name}", daemon=True)
        watcher.start()
        return True

    def release(self) -> None:
        snapshot = self._read_snapshot(self.lock_path)

        if snapshot is None or snapshot.payload is None:
            return

        if snapshot.payload.get("token") != self.token:
            return

        self._remove_if_unchanged(self.lock_path, snapshot)

    @classmethod
    def is_active(cls, instance: Instance) -> bool:
        snapshot = cls._read_snapshot(cls.lock_path_for(instance))
        return snapshot is not None and cls._snapshot_is_active(snapshot)

    @classmethod
    def owns_preparing_lock(cls, instance: Instance, token: str | None) -> bool:
        if not isinstance(token, str) or not token:
            return False

        snapshot = cls._read_snapshot(cls.lock_path_for(instance))
        if snapshot is None or snapshot.payload is None or not cls._snapshot_is_active(snapshot):
            return False

        payload = snapshot.payload
        return (
            payload.get("token") == token
            and payload.get("state") == "preparing"
            and cls._read_pid(payload.get("launcher_pid")) == os.getpid()
            and cls._read_pid(payload.get("minecraft_pid")) is None
        )

    @classmethod
    def active_for(cls, instance: Instance) -> RunningInstanceInfo | None:
        lock_path = cls.lock_path_for(instance)
        snapshot = cls._read_snapshot(lock_path)
        if snapshot is None:
            return None
        if not cls._snapshot_is_active(snapshot):
            cls._remove_if_unchanged(lock_path, snapshot)
            return None
        return cls._running_instance_from_payload(snapshot.payload)

    @classmethod
    def remove_for(cls, instance: Instance, force: bool = False) -> bool:
        lock_path = cls.lock_path_for(instance)
        snapshot = cls._read_snapshot(lock_path)
        if snapshot is None:
            return True
        if cls._snapshot_is_active(snapshot) and not force:
            return False
        return cls._remove_if_unchanged(lock_path, snapshot)

    @classmethod
    def reconcile(cls) -> tuple[str, ...]:
        Paths.INSTANCE_LOCKS_ROOT.mkdir(parents=True, exist_ok=True)
        removed: list[str] = []
        try:
            lock_paths = list(Paths.INSTANCE_LOCKS_ROOT.glob("*.lock"))
        except OSError:
            return ()

        for lock_path in lock_paths:
            snapshot = cls._read_snapshot(lock_path)
            if snapshot is None:
                continue
            if cls._snapshot_is_active(snapshot):
                continue
            if cls._remove_if_unchanged(lock_path, snapshot):
                name = ""
                if snapshot.payload is not None:
                    name = str(snapshot.payload.get("instance_name") or "")
                removed.append(name or lock_path.stem)
        return tuple(sorted(removed, key=str.casefold))

    @classmethod
    def list_active(cls) -> list[RunningInstanceInfo]:
        Paths.INSTANCE_LOCKS_ROOT.mkdir(parents=True, exist_ok=True)
        running_instances: list[RunningInstanceInfo] = []

        try:
            lock_paths = list(Paths.INSTANCE_LOCKS_ROOT.glob("*.lock"))
        except OSError:
            return running_instances

        for lock_path in lock_paths:
            snapshot = cls._read_snapshot(lock_path)

            if snapshot is None:
                continue

            if not cls._snapshot_is_active(snapshot):
                cls._remove_if_unchanged(lock_path, snapshot)
                continue

            running_instance = cls._running_instance_from_payload(snapshot.payload)

            if running_instance is not None:
                running_instances.append(running_instance)

        return sorted(running_instances, key=lambda item: item.name.casefold())

    @classmethod
    def lock_path_for(cls, instance: Instance) -> Path:
        Paths.INSTANCE_LOCKS_ROOT.mkdir(parents=True, exist_ok=True)
        identity = cls._instance_identity(instance)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return Paths.INSTANCE_LOCKS_ROOT / f"{digest}.lock"

    def _wait_and_release(self, process: Any) -> None:
        try:
            process.wait()
        finally:
            self.release()

    def _update_owned_lock(self, state: str, minecraft_pid: int | None) -> None:
        snapshot = self._read_snapshot(self.lock_path)

        if snapshot is None or snapshot.payload is None:
            return

        if snapshot.payload.get("token") != self.token:
            return

        payload = dict(snapshot.payload)
        payload.update({"state": state, "minecraft_pid": minecraft_pid, "updated_at": self._utc_now()})
        self._replace_lock_file(self.lock_path, payload)

    @classmethod
    def _instance_identity(cls, instance: Instance) -> str:
        instance_id = str(getattr(instance, "instance_id", "")).strip()

        if instance_id:
            return f"id:{instance_id}"

        instance_dir = getattr(instance, "instance_dir", None)
        resolved_dir = Path(instance_dir) if instance_dir is not None else Paths.load_instance_dir(instance.name)
        return f"path:{os.path.normcase(str(resolved_dir.resolve()))}"

    @classmethod
    def _running_instance_from_payload(cls, payload: dict[str, Any] | None) -> RunningInstanceInfo | None:
        if payload is None:
            return None

        name = payload.get("instance_name")

        if not isinstance(name, str) or not name.strip():
            return None

        minecraft_pid = cls._read_pid(payload.get("minecraft_pid"))
        state = payload.get("state")

        if state not in {"preparing", "running"}:
            state = "running" if minecraft_pid is not None else "preparing"

        instance_id = payload.get("instance_id")

        return RunningInstanceInfo(
            instance_id=instance_id if isinstance(instance_id, str) and instance_id else None,
            name=name.strip(),
            state=state,
            launcher_pid=cls._read_pid(payload.get("launcher_pid")),
            minecraft_pid=minecraft_pid,
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
        )

    @classmethod
    def _build_payload(cls, instance: Instance, token: str, state: str, minecraft_pid: int | None) -> dict[str, Any]:
        now = cls._utc_now()
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "token": token,
            "instance_id": getattr(instance, "instance_id", None),
            "instance_name": instance.name,
            "state": state,
            "launcher_pid": os.getpid(),
            "minecraft_pid": minecraft_pid,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _create_lock_file(lock_path: Path, payload: dict[str, Any]) -> None:
        file_descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)

        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as lock_file:
                json.dump(payload, lock_file, indent=2, ensure_ascii=False)
                lock_file.flush()
                os.fsync(lock_file.fileno())
        except Exception:
            lock_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _replace_lock_file(lock_path: Path, payload: dict[str, Any]) -> None:
        temporary_path = lock_path.with_name(f"{lock_path.name}.{payload['token']}.tmp")

        try:
            with temporary_path.open("w", encoding="utf-8") as lock_file:
                json.dump(payload, lock_file, indent=2, ensure_ascii=False)
                lock_file.flush()
                os.fsync(lock_file.fileno())

            os.replace(temporary_path, lock_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @classmethod
    def _read_snapshot(cls, lock_path: Path) -> _LockSnapshot | None:
        try:
            before = lock_path.stat()
            raw_payload = lock_path.read_text(encoding="utf-8")
            after = lock_path.stat()
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError):
            try:
                stat = lock_path.stat()
            except OSError:
                return None

            return _LockSnapshot(payload=None, identity=cls._stat_identity(stat), age_seconds=max(0.0, time.time() - stat.st_mtime))

        before_identity = cls._stat_identity(before)
        after_identity = cls._stat_identity(after)

        if before_identity != after_identity:
            return None

        try:
            payload = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            payload = None

        if not isinstance(payload, dict):
            payload = None

        return _LockSnapshot(payload=payload, identity=after_identity, age_seconds=max(0.0, time.time() - after.st_mtime))

    @classmethod
    def _snapshot_is_active(cls, snapshot: _LockSnapshot) -> bool:
        if snapshot.payload is None:
            return snapshot.age_seconds < cls.MALFORMED_LOCK_GRACE_SECONDS

        launcher_pid = cls._read_pid(snapshot.payload.get("launcher_pid"))
        minecraft_pid = cls._read_pid(snapshot.payload.get("minecraft_pid"))
        state = snapshot.payload.get("state")

        if state == "running" and minecraft_pid is not None:
            return cls._is_process_alive(minecraft_pid)

        if launcher_pid is not None:
            return cls._is_process_alive(launcher_pid)

        return False

    @classmethod
    def _remove_if_unchanged(cls, lock_path: Path, snapshot: _LockSnapshot) -> bool:
        try:
            current = lock_path.stat()
        except FileNotFoundError:
            return True
        except OSError:
            return False

        if cls._stat_identity(current) != snapshot.identity:
            return False

        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    @staticmethod
    def _stat_identity(stat: os.stat_result) -> tuple[int, int, int, int]:
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size

    @staticmethod
    def _read_pid(value: Any) -> int | None:
        if isinstance(value, bool):
            return None

        if isinstance(value, int) and value > 0:
            return value

        return None

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        if pid == os.getpid():
            return True

        if os.name == "nt":
            return InstanceRunLock._is_windows_process_alive(pid)

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False

        return True

    @staticmethod
    def _is_windows_process_alive(pid: int) -> bool:
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        process_handle = kernel32.OpenProcess(process_query_limited_information, False, pid)

        if not process_handle:
            return ctypes.get_last_error() == error_access_denied

        try:
            exit_code = wintypes.DWORD()

            if not kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
                return True

            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(process_handle)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
