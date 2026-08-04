from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from src.core.fs.paths import Paths
from src.core.java.java_runtime import JavaRuntime
from src.core.runtime.process_supervisor import ProcessSupervisor
from src.models.instance.instance import Instance
from src.models.runtime.game_exit_result import GameExitResult


GameExitCallback = Callable[[GameExitResult], None]


class GameRuntimeManager:
    HISTORY_SCHEMA_VERSION = 1
    HISTORY_LIMIT = 50
    POLL_INTERVAL_SECONDS = 0.5
    _active_processes: dict[str, object] = {}
    _active_processes_lock = threading.RLock()

    @classmethod
    def watch(cls, process: object, instance: Instance, minecraft_version: str, started_at: datetime, on_exit: GameExitCallback | None = None, session_id: str | None = None, crash_report_snapshot: Mapping[str, tuple[int, int]] | None = None) -> bool:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return False

        cls._register_process(instance, process)
        snapshot = dict(crash_report_snapshot) if crash_report_snapshot is not None else cls.crash_report_snapshot(instance)
        watcher = threading.Thread(target=cls._watch_process, args=(process, instance, minecraft_version, started_at, on_exit, session_id, snapshot), name=f"game-runtime-{instance.name}", daemon=True)
        watcher.start()
        return True

    @classmethod
    def _watch_process(cls, process: object, instance: Instance, minecraft_version: str, started_at: datetime, on_exit: GameExitCallback | None, session_id: str | None = None, crash_report_snapshot: Mapping[str, tuple[int, int]] | None = None) -> None:
        try:
            exit_code = cls._wait_for_exit(process)
            ended_at = datetime.now(timezone.utc)
            log_path = JavaRuntime.log_path(process) or cls.latest_game_log(instance)
            JavaRuntime.close_process_log(process)
            crash_report_path = cls.latest_crash_report(instance, since=started_at, previous=crash_report_snapshot)
            stopped_by_launcher = ProcessSupervisor.stop_requested(session_id)
            crashed = not stopped_by_launcher and (exit_code != 0 or crash_report_path is not None)
            duration_seconds = max(0, round((ended_at - started_at).total_seconds()))
            pid = getattr(process, "pid", None)
            result = GameExitResult(
                instance_name=instance.name,
                minecraft_version=minecraft_version,
                pid=pid if isinstance(pid, int) and pid > 0 else None,
                exit_code=exit_code,
                started_at=started_at.isoformat(),
                ended_at=ended_at.isoformat(),
                duration_seconds=duration_seconds,
                crashed=crashed,
                session_id=session_id,
                stopped_by_launcher=stopped_by_launcher,
                log_path=log_path,
                crash_report_path=crash_report_path,
            )
            try:
                cls._record_result(instance, result)
            finally:
                if session_id:
                    try:
                        ProcessSupervisor.finish(session_id, exit_code, crashed)
                    except Exception:
                        pass
                if on_exit is not None:
                    try:
                        on_exit(result)
                    except Exception:
                        pass
        finally:
            cls._unregister_process(instance, process)

    @classmethod
    def stop(cls, instance: Instance, graceful_timeout: float = 2.5) -> bool:
        supervised = ProcessSupervisor.active_for(instance)
        if supervised is not None:
            process = cls._active_process(instance)
            stopped = ProcessSupervisor.stop_instance(instance, graceful_timeout=graceful_timeout)
            if stopped and process is not None:
                cls._unregister_process(instance, process)
            return stopped

        process = cls._active_process(instance)
        if process is None:
            return False
        poll = getattr(process, "poll", None)
        if callable(poll):
            try:
                if poll() is not None:
                    cls._unregister_process(instance, process)
                    return False
            except Exception:
                pass
        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            try:
                terminate()
            except Exception:
                pass
        if cls._wait_process(process, graceful_timeout):
            cls._unregister_process(instance, process)
            return True
        kill = getattr(process, "kill", None)
        if callable(kill):
            try:
                kill()
            except Exception:
                pass
        if cls._wait_process(process, 2.0):
            cls._unregister_process(instance, process)
        return True

    @classmethod
    def _register_process(cls, instance: Instance, process: object) -> None:
        with cls._active_processes_lock:
            cls._active_processes[cls._instance_key(instance)] = process

    @classmethod
    def _unregister_process(cls, instance: Instance, process: object) -> None:
        key = cls._instance_key(instance)
        with cls._active_processes_lock:
            if cls._active_processes.get(key) is process:
                cls._active_processes.pop(key, None)

    @classmethod
    def _active_process(cls, instance: Instance) -> object | None:
        with cls._active_processes_lock:
            return cls._active_processes.get(cls._instance_key(instance))

    @staticmethod
    def _instance_key(instance: Instance) -> str:
        instance_id = str(getattr(instance, "instance_id", "")).strip()
        if instance_id:
            return f"id:{instance_id}"
        return f"path:{os.path.normcase(str(Path(instance.instance_dir).resolve(strict=False)))}"

    @staticmethod
    def _wait_process(process: object, timeout: float) -> bool:
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
    def _wait_for_exit(cls, process: object) -> int:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return -1
        while True:
            try:
                result = poll()
            except Exception:
                return -1
            if result is not None:
                try:
                    return int(result)
                except (TypeError, ValueError):
                    return -1
            time.sleep(cls.POLL_INTERVAL_SECONDS)

    @staticmethod
    def latest_game_log(instance: Instance) -> Path | None:
        return GameRuntimeManager._latest_file(Paths.instance_logs_dir(instance), "minecraft-*.log")

    @staticmethod
    def crash_report_snapshot(instance: Instance) -> dict[str, tuple[int, int]]:
        directory = Paths.instance_crash_reports_dir(instance)
        snapshot: dict[str, tuple[int, int]] = {}
        try:
            paths = tuple(directory.glob("*.txt"))
        except OSError:
            return snapshot
        for path in paths:
            if not path.is_file():
                continue
            try:
                stat_result = path.stat()
                snapshot[os.path.normcase(str(path.resolve(strict=False)))] = (int(stat_result.st_mtime_ns), int(stat_result.st_size))
            except OSError:
                continue
        return snapshot

    @staticmethod
    def latest_crash_report(instance: Instance, since: datetime | None = None, previous: Mapping[str, tuple[int, int]] | None = None) -> Path | None:
        directory = Paths.instance_crash_reports_dir(instance)
        candidates: list[Path] = []
        baseline = dict(previous or {})
        try:
            paths = tuple(directory.glob("*.txt"))
        except OSError:
            return None
        for path in paths:
            if not path.is_file():
                continue
            try:
                stat_result = path.stat()
            except OSError:
                continue
            signature = (int(stat_result.st_mtime_ns), int(stat_result.st_size))
            key = os.path.normcase(str(path.resolve(strict=False)))
            if previous is not None:
                if baseline.get(key) == signature:
                    continue
            elif since is not None and stat_result.st_mtime < since.timestamp():
                continue
            candidates.append(path)
        if not candidates:
            return None
        try:
            return max(candidates, key=lambda item: item.stat().st_mtime_ns)
        except OSError:
            return sorted(candidates, key=lambda item: item.name.casefold())[-1]

    @staticmethod
    def _latest_file(directory: Path, pattern: str) -> Path | None:
        try:
            files = [path for path in directory.glob(pattern) if path.is_file()]
        except OSError:
            return None
        if not files:
            return None
        try:
            return max(files, key=lambda path: path.stat().st_mtime)
        except OSError:
            return sorted(files, key=lambda path: path.name.casefold())[-1]

    @classmethod
    def record_start(cls, instance: Instance, started_at: datetime, session_id: str | None) -> None:
        path = Paths.instance_metadata(instance.name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        data["last_started_at"] = started_at.isoformat()
        data["last_session_id"] = str(session_id or "")
        cls._write_json_atomic(path, data)

    @classmethod
    def _record_result(cls, instance: Instance, result: GameExitResult) -> None:
        try:
            cls._append_history(instance, result)
        except OSError:
            pass
        try:
            cls._update_instance_metadata(instance, result)
        except OSError:
            pass

    @classmethod
    def _append_history(cls, instance: Instance, result: GameExitResult) -> None:
        path = Paths.instance_runtime_history(instance)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError, ValueError):
            data = {}
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            records = []
        records.append(result.to_dict())
        payload = {"schema_version": cls.HISTORY_SCHEMA_VERSION, "records": records[-cls.HISTORY_LIMIT:]}
        cls._write_json_atomic(path, payload)

    @classmethod
    def _update_instance_metadata(cls, instance: Instance, result: GameExitResult) -> None:
        path = Paths.instance_metadata(instance.name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        current_session = str(data.get("last_session_id") or "")
        if current_session and result.session_id and current_session != result.session_id:
            return
        current_started = str(data.get("last_started_at") or "")
        if current_started and current_started > result.started_at:
            return
        previous_play_time = data.get("total_play_time_seconds", 0)
        try:
            total_play_time = max(0, int(previous_play_time)) + result.duration_seconds
        except (TypeError, ValueError):
            total_play_time = result.duration_seconds
        data.update({
            "updated_at": result.ended_at,
            "last_played": result.ended_at,
            "total_play_time_seconds": total_play_time,
            "last_exit_code": result.exit_code,
            "last_launch_crashed": result.crashed,
            "last_launch_state": "crashed" if result.crashed else "finished",
            "last_started_at": result.started_at,
            "last_finished_at": result.ended_at,
            "last_session_id": str(result.session_id or current_session),
            "last_stop_requested": bool(result.stopped_by_launcher),
            "last_game_log": str(result.log_path) if result.log_path is not None else "",
            "last_crash_report": str(result.crash_report_path) if result.crash_report_path is not None else "",
        })
        cls._write_json_atomic(path, data)

    @staticmethod
    def _write_json_atomic(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        payload = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
