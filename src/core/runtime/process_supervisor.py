from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.fs.paths import Paths
from src.core.system.platform_info import PlatformInfo
from src.core.instance.instance_run_lock import InstanceRunLock
from src.models.instance.instance import Instance
from src.models.runtime.process_session import ProcessSession, ProcessSessionState


class ProcessSupervisor:
    """Persist and supervise Minecraft process sessions without touching unrelated Java processes."""

    SCHEMA_VERSION = 1
    HISTORY_LIMIT = 100
    _processes: dict[str, object] = {}
    _sessions_by_instance: dict[str, str] = {}
    _lock = threading.RLock()

    @classmethod
    def begin(cls, instance: Instance) -> ProcessSession:
        session_id = uuid.uuid4().hex
        now = cls._now()
        instance_name = str(getattr(instance, "name", "") or "").strip()
        if not instance_name:
            raise ValueError("Instance name cannot be empty.")
        instance_dir = cls._instance_dir(instance)
        session = ProcessSession(
            session_id=session_id,
            instance_id=str(getattr(instance, "instance_id", "") or ""),
            instance_name=instance_name,
            instance_dir=instance_dir,
            state=ProcessSessionState.PREPARING,
            launcher_pid=os.getpid(),
            root_pid=None,
            child_pids=(),
            started_at=now,
            updated_at=now,
        )
        cls._write_active(session)
        with cls._lock:
            cls._sessions_by_instance[cls._instance_key(instance)] = session_id
        return session

    @classmethod
    def attach(cls, session_id: str, process: object) -> ProcessSession:
        pid = cls._read_pid(getattr(process, "pid", None))
        session = cls.load(session_id)
        updated = cls._replace(session, state=ProcessSessionState.RUNNING, root_pid=pid, updated_at=cls._now())
        cls._write_active(updated)
        with cls._lock:
            cls._processes[session_id] = process
        return updated

    @classmethod
    def register_child(cls, session_id: str, pid: int) -> ProcessSession:
        child_pid = cls._read_pid(pid)
        if child_pid is None:
            raise ValueError("Child PID must be a positive integer.")
        session = cls.load(session_id)
        children = tuple(sorted({*session.child_pids, child_pid}))
        updated = cls._replace(session, child_pids=children, updated_at=cls._now())
        cls._write_active(updated)
        return updated

    @classmethod
    def finish(cls, session_id: str, exit_code: int, crashed: bool, detail: str = "") -> ProcessSession | None:
        try:
            session = cls.load(session_id)
        except (FileNotFoundError, RuntimeError):
            cls._forget(session_id)
            return None
        now = cls._now()
        final = cls._replace(
            session,
            state=ProcessSessionState.CRASHED if crashed else ProcessSessionState.FINISHED,
            exit_code=int(exit_code),
            ended_at=now,
            updated_at=now,
            detail=str(detail or ""),
        )
        cls._archive(final)
        cls._forget(session_id)
        return final

    @classmethod
    def abort(cls, session_id: str, detail: str = "") -> ProcessSession | None:
        try:
            session = cls.load(session_id)
        except (FileNotFoundError, RuntimeError):
            cls._forget(session_id)
            return None
        now = cls._now()
        final = cls._replace(
            session,
            state=ProcessSessionState.INTERRUPTED,
            ended_at=now,
            updated_at=now,
            detail=str(detail or "launch_interrupted"),
        )
        cls._archive(final)
        cls._forget(session_id)
        return final

    @classmethod
    def stop_requested(cls, session_id: str | None) -> bool:
        if not session_id:
            return False
        try:
            return cls.load(session_id).state in {ProcessSessionState.STOPPING, ProcessSessionState.KILLING}
        except (FileNotFoundError, RuntimeError):
            return False

    @classmethod
    def kill_requested(cls, session_id: str | None) -> bool:
        if not session_id:
            return False
        try:
            return cls.load(session_id).state is ProcessSessionState.KILLING
        except (FileNotFoundError, RuntimeError):
            return False

    @classmethod
    def active_for(cls, instance: Instance) -> ProcessSession | None:
        key = cls._instance_key(instance)
        with cls._lock:
            session_id = cls._sessions_by_instance.get(key)
        if session_id:
            try:
                session = cls.load(session_id)
            except (FileNotFoundError, RuntimeError):
                with cls._lock:
                    cls._sessions_by_instance.pop(key, None)
            else:
                if session.active:
                    return session
        for session in cls.list_active():
            if cls._matches_instance(session, instance):
                with cls._lock:
                    cls._sessions_by_instance[key] = session.session_id
                return session
        return None

    @classmethod
    def list_active(cls) -> tuple[ProcessSession, ...]:
        root = Paths.process_sessions_root()
        sessions: list[ProcessSession] = []
        try:
            paths = tuple(root.glob("*.json"))
        except OSError:
            return ()
        for path in paths:
            try:
                session = cls._read(path)
            except RuntimeError:
                continue
            if session.active:
                sessions.append(session)
        return tuple(sorted(sessions, key=lambda item: item.instance_name.casefold()))

    @classmethod
    def stop_process(cls, process: object, graceful_timeout: float = 2.5) -> bool:
        """Stop a process object already created by MCW without inspecting unrelated system processes."""
        return cls._stop_process_object(process, graceful_timeout)

    @classmethod
    def stop_instance(cls, instance: Instance, graceful_timeout: float = 2.5) -> bool:
        session = cls.active_for(instance)
        if session is None:
            return False
        process = None
        with cls._lock:
            process = cls._processes.get(session.session_id)
        stopping = cls._replace(session, state=ProcessSessionState.STOPPING, updated_at=cls._now())
        cls._write_active(stopping)

        stopped = False
        if process is not None:
            process_pid = cls._read_pid(getattr(process, "pid", None))
            if process_pid is not None and cls._pid_matches_instance(process_pid, session.instance_dir):
                cls._terminate_pid_tree(process_pid, force=False)
                cls._wait_for_exit(process_pid, graceful_timeout)
                if cls._pid_alive(process_pid):
                    cls._terminate_pid_tree(process_pid, force=True)
                    cls._wait_for_exit(process_pid, 2.0)
                stopped = not cls._pid_alive(process_pid)
            else:
                stopped = cls._stop_process_object(process, graceful_timeout)
        elif session.root_pid is not None and cls._pid_matches_instance(session.root_pid, session.instance_dir):
            cls._terminate_pid_tree(session.root_pid, force=False)
            cls._wait_for_exit(session.root_pid, graceful_timeout)
            if cls._pid_alive(session.root_pid):
                cls._terminate_pid_tree(session.root_pid, force=True)
                cls._wait_for_exit(session.root_pid, 2.0)
            stopped = not cls._pid_alive(session.root_pid)

        children_stopped = cls._stop_registered_children(session, graceful_timeout)
        stopped = stopped and children_stopped
        if stopped and process is None:
            cls.abort(session.session_id, "stopped_by_launcher")
        return stopped

    @classmethod
    def kill_instance(cls, instance: Instance, timeout: float = 1.5) -> bool:
        """Force-kill the verified Minecraft process tree for one MCW launch session."""
        session = cls.active_for(instance)
        if session is None:
            return False
        with cls._lock:
            process = cls._processes.get(session.session_id)
        killing = cls._replace(
            session,
            state=ProcessSessionState.KILLING,
            updated_at=cls._now(),
            detail="killed_by_user",
        )
        cls._write_active(killing)

        stopped = False
        if process is not None:
            process_pid = cls._read_pid(getattr(process, "pid", None))
            if process_pid is not None and cls._pid_matches_instance(process_pid, session.instance_dir):
                cls._terminate_pid_tree(process_pid, force=True)
                cls._wait_for_exit(process_pid, timeout)
                stopped = not cls._pid_alive(process_pid)
            else:
                stopped = cls._kill_process_object(process, timeout)
        elif session.root_pid is not None and cls._pid_matches_instance(session.root_pid, session.instance_dir):
            cls._terminate_pid_tree(session.root_pid, force=True)
            cls._wait_for_exit(session.root_pid, timeout)
            stopped = not cls._pid_alive(session.root_pid)

        children_stopped = cls._kill_registered_children(session, timeout)
        stopped = stopped and children_stopped
        if stopped and process is None:
            cls.abort(session.session_id, "killed_by_user")
        return stopped

    @classmethod
    def reconcile(cls) -> tuple[str, ...]:
        interrupted: list[str] = []
        root = Paths.process_sessions_root()
        for path in tuple(root.glob("*.json")):
            try:
                session = cls._read(path)
            except RuntimeError:
                path.unlink(missing_ok=True)
                continue
            root_alive = session.root_pid is not None and cls._pid_alive(session.root_pid)
            launcher_alive = session.launcher_pid is not None and cls._pid_alive(session.launcher_pid)
            if root_alive and cls._pid_matches_instance(session.root_pid or 0, session.instance_dir):
                continue
            if session.state is ProcessSessionState.PREPARING and launcher_alive:
                continue
            cls.abort(session.session_id, "recovered_stale_process_session")
            interrupted.append(session.instance_name)
        return tuple(sorted(dict.fromkeys(interrupted), key=str.casefold))

    @classmethod
    def load(cls, session_id: str) -> ProcessSession:
        path = Paths.process_sessions_root() / f"{session_id}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return cls._read(path)

    @classmethod
    def _read(cls, path: Path) -> ProcessSession:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid process session: {path}") from error
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid process session: {path}")
        try:
            state = ProcessSessionState(str(payload["state"]))
            session_id = str(payload["session_id"]).strip()
            instance_name = str(payload["instance_name"]).strip()
            instance_dir = Path(str(payload["instance_dir"])).resolve(strict=False)
            child_pids = tuple(pid for pid in (cls._read_pid(value) for value in payload.get("child_pids", ())) if pid is not None)
            if not session_id or not instance_name:
                raise ValueError("missing identity")
            return ProcessSession(
                session_id=session_id,
                instance_id=str(payload.get("instance_id") or ""),
                instance_name=instance_name,
                instance_dir=instance_dir,
                state=state,
                launcher_pid=cls._read_pid(payload.get("launcher_pid")),
                root_pid=cls._read_pid(payload.get("root_pid")),
                child_pids=child_pids,
                started_at=str(payload.get("started_at") or ""),
                updated_at=str(payload.get("updated_at") or ""),
                ended_at=str(payload.get("ended_at") or ""),
                exit_code=int(payload["exit_code"]) if payload.get("exit_code") is not None else None,
                detail=str(payload.get("detail") or ""),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid process session: {path}") from error

    @classmethod
    def _write_active(cls, session: ProcessSession) -> None:
        path = Paths.process_sessions_root() / f"{session.session_id}.json"
        cls._write_json_atomic(path, session.to_dict())

    @classmethod
    def _archive(cls, session: ProcessSession) -> None:
        active_path = Paths.process_sessions_root() / f"{session.session_id}.json"
        history_path = Paths.process_session_history_root() / f"{session.session_id}.json"
        cls._write_json_atomic(history_path, session.to_dict())
        active_path.unlink(missing_ok=True)
        cls._prune_history()

    @classmethod
    def _prune_history(cls) -> None:
        root = Paths.process_session_history_root()
        try:
            paths = [path for path in root.glob("*.json") if path.is_file()]
            paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return
        for path in paths[cls.HISTORY_LIMIT:]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @classmethod
    def _forget(cls, session_id: str) -> None:
        with cls._lock:
            cls._processes.pop(session_id, None)
            keys = [key for key, value in cls._sessions_by_instance.items() if value == session_id]
            for key in keys:
                cls._sessions_by_instance.pop(key, None)

    @staticmethod
    def _replace(session: ProcessSession, **changes: Any) -> ProcessSession:
        data = {
            "session_id": session.session_id,
            "instance_id": session.instance_id,
            "instance_name": session.instance_name,
            "instance_dir": session.instance_dir,
            "state": session.state,
            "launcher_pid": session.launcher_pid,
            "root_pid": session.root_pid,
            "child_pids": session.child_pids,
            "started_at": session.started_at,
            "updated_at": session.updated_at,
            "ended_at": session.ended_at,
            "exit_code": session.exit_code,
            "detail": session.detail,
        }
        data.update(changes)
        return ProcessSession(**data)

    @classmethod
    def _matches_instance(cls, session: ProcessSession, instance: Instance) -> bool:
        instance_id = str(getattr(instance, "instance_id", "") or "")
        if instance_id and session.instance_id == instance_id:
            return True
        try:
            return session.instance_dir == cls._instance_dir(instance)
        except OSError:
            return session.instance_name == str(getattr(instance, "name", "") or "")

    @classmethod
    def _instance_key(cls, instance: Instance) -> str:
        instance_id = str(getattr(instance, "instance_id", "") or "").strip()
        if instance_id:
            return f"id:{instance_id}"
        return f"path:{os.path.normcase(str(cls._instance_dir(instance)))}"

    @staticmethod
    def _instance_dir(instance: Instance) -> Path:
        name = str(getattr(instance, "name", "") or "").strip()
        value = getattr(instance, "instance_dir", None)
        return Path(value if value is not None else Paths.load_instance_dir(name)).resolve(strict=False)

    @staticmethod
    def _read_pid(value: object) -> int | None:
        try:
            pid = int(value)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        return InstanceRunLock._is_process_alive(pid)

    @classmethod
    def _stop_process_object(cls, process: object, graceful_timeout: float) -> bool:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return False
        try:
            if poll() is not None:
                return True
        except Exception:
            return False
        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            try:
                terminate()
            except Exception:
                pass
        if cls._wait_process_object(process, graceful_timeout):
            return True
        kill = getattr(process, "kill", None)
        if callable(kill):
            try:
                kill()
            except Exception:
                pass
        return cls._wait_process_object(process, 2.0)

    @classmethod
    def _kill_process_object(cls, process: object, timeout: float) -> bool:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return False
        try:
            if poll() is not None:
                return True
        except Exception:
            return False
        kill = getattr(process, "kill", None)
        if not callable(kill):
            return False
        try:
            kill()
        except Exception:
            return False
        return cls._wait_process_object(process, timeout)

    @staticmethod
    def _wait_process_object(process: object, timeout: float) -> bool:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return False
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            try:
                if poll() is not None:
                    return True
            except Exception:
                return False
            time.sleep(0.05)
        try:
            return poll() is not None
        except Exception:
            return False

    @classmethod
    def _stop_registered_children(cls, session: ProcessSession, graceful_timeout: float) -> bool:
        all_stopped = True
        for pid in reversed(session.child_pids):
            if not cls._pid_alive(pid):
                continue
            if not cls._pid_matches_instance(pid, session.instance_dir):
                all_stopped = False
                continue
            cls._terminate_pid_tree(pid, force=False)
            cls._wait_for_exit(pid, graceful_timeout)
            if cls._pid_alive(pid):
                cls._terminate_pid_tree(pid, force=True)
                cls._wait_for_exit(pid, 2.0)
            all_stopped = all_stopped and not cls._pid_alive(pid)
        return all_stopped

    @classmethod
    def _kill_registered_children(cls, session: ProcessSession, timeout: float) -> bool:
        all_stopped = True
        for pid in reversed(session.child_pids):
            if not cls._pid_alive(pid):
                continue
            if not cls._pid_matches_instance(pid, session.instance_dir):
                all_stopped = False
                continue
            cls._terminate_pid_tree(pid, force=True)
            cls._wait_for_exit(pid, timeout)
            all_stopped = all_stopped and not cls._pid_alive(pid)
        return all_stopped

    @classmethod
    def _pid_matches_instance(cls, pid: int, instance_dir: Path) -> bool:
        if pid <= 0 or pid == os.getpid():
            return False
        needle = os.path.normcase(str(instance_dir.resolve(strict=False)))
        if PlatformInfo.is_windows():
            script = (
                f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' -ErrorAction SilentlyContinue; "
                "if ($p -and $p.CommandLine) { [Console]::Out.Write($p.CommandLine) }"
            )
            try:
                completed = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return False
            command_line = os.path.normcase(completed.stdout.strip())
            return completed.returncode == 0 and bool(command_line) and needle in command_line
        proc_cmdline = Path("/proc") / str(pid) / "cmdline"
        try:
            command_line = os.path.normcase(proc_cmdline.read_bytes().replace(b"\x00", b" ").decode(errors="replace"))
        except OSError:
            return False
        return needle in command_line

    @staticmethod
    def _terminate_pid_tree(pid: int, force: bool) -> None:
        if pid <= 0 or pid == os.getpid():
            return
        if PlatformInfo.is_windows():
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
            target_signal = signal.SIGKILL if force else signal.SIGTERM
            group_id = os.getpgid(pid)
            if group_id == pid and group_id != os.getpgrp():
                os.killpg(group_id, target_signal)
                return
            os.kill(pid, target_signal)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            except OSError:
                pass

    @classmethod
    def _wait_for_exit(cls, pid: int, timeout: float) -> None:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            if not cls._pid_alive(pid):
                return
            time.sleep(0.05)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
