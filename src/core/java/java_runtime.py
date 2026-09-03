from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TextIO

from dataclasses import dataclass

from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.paths import Paths
from src.core.hardware.gpu_preference_manager import GpuPreferenceManager
from src.core.java.java_command_compactor import JavaCommandCompactor
from src.core.system.platform_info import PlatformInfo
from src.models.instance.instance import Instance




@dataclass(frozen=True, slots=True)
class JavaStartupProbe:
    exit_code: int
    log_path: Path | None
    output: str
    java_runtime_failure: bool


class JavaRuntime:
    _process_logs: dict[int, Path] = {}
    _process_logs_lock = threading.RLock()

    @classmethod
    def run(cls, java: Path, command: list[str], instance: Instance) -> subprocess.Popen:
        creation_flags = subprocess.CREATE_NO_WINDOW if PlatformInfo.is_windows() else 0
        log_dir = Paths.instance_logs_dir(instance)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = cls._unique_log_path(log_dir, timestamp)
        log_file = log_path.open("w", encoding="utf-8", errors="replace")

        instance_dir = Paths.load_instance_dir(instance.name)
        try:
            launch_command = JavaCommandCompactor.prepare(java, command, instance_dir)
        except Exception:
            log_file.close()
            raise

        try:
            settings = LauncherSettingsManager().load()
            prefer_dedicated_gpu = bool(settings.get("launch", {}).get("prefer_dedicated_gpu", False))
            GpuPreferenceManager.apply_to_java(java, prefer_dedicated_gpu)
            process = cls._popen(java, launch_command, instance_dir, log_file, creation_flags)
        except OSError as error:
            if not cls._is_windows_length_error(error):
                log_file.close()
                raise

            compacted = JavaCommandCompactor.prepare(java, command, instance_dir, force=True)
            if compacted == launch_command:
                log_file.close()
                raise cls._windows_length_error(instance_dir) from error
            try:
                process = cls._popen(java, compacted, instance_dir, log_file, creation_flags)
            except OSError as retry_error:
                log_file.close()
                if cls._is_windows_length_error(retry_error):
                    raise cls._windows_length_error(instance_dir) from retry_error
                raise
            except Exception:
                log_file.close()
                raise
        except Exception:
            log_file.close()
            raise

        log_file.close()
        pid = getattr(process, "pid", None)
        if isinstance(pid, int) and pid > 0:
            with cls._process_logs_lock:
                cls._process_logs[pid] = log_path
        return process

    @staticmethod
    def _unique_log_path(log_dir: Path, timestamp: str) -> Path:
        base = log_dir / f"minecraft-{timestamp}.log"
        if not base.exists():
            return base
        for index in range(1, 1000):
            candidate = log_dir / f"minecraft-{timestamp}-{index}.log"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not allocate a unique Minecraft log file in: {log_dir}")

    @staticmethod
    def _popen(java: Path, command: list[str], instance_dir: Path, log_file: TextIO, creation_flags: int) -> subprocess.Popen:
        options = {
            "cwd": instance_dir,
            "stdin": subprocess.DEVNULL,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "creationflags": creation_flags,
        }
        if not PlatformInfo.is_windows():
            # Give each Minecraft launch its own process group so the
            # supervisor can stop loader/Java descendants without touching
            # the launcher or unrelated Java processes.
            options["start_new_session"] = True
        return subprocess.Popen([str(java), *command], **options)

    @staticmethod
    def _is_windows_length_error(error: OSError) -> bool:
        return PlatformInfo.is_windows() and getattr(error, "winerror", None) == 206

    @staticmethod
    def _windows_length_error(instance_dir: Path) -> RuntimeError:
        return RuntimeError(
            "Windows could not start Minecraft because the launch command or one of its paths is still too long. "
            f"Move MCW Launcher to a shorter folder such as C:\\MCW and shorten the instance name if needed. Instance: {instance_dir}"
        )


    @classmethod
    def probe_startup(cls, process: object, timeout_seconds: float = 1.25, poll_interval: float = 0.05) -> JavaStartupProbe | None:
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return None

        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        exit_code = poll()
        if exit_code is None and not isinstance(process, subprocess.Popen):
            return None
        while exit_code is None and time.monotonic() < deadline:
            time.sleep(max(0.01, float(poll_interval)))
            exit_code = poll()
        if exit_code is None:
            return None

        log_path = cls.log_path(process)
        output = cls._read_log(log_path)
        return JavaStartupProbe(
            exit_code=int(exit_code),
            log_path=log_path,
            output=output,
            java_runtime_failure=cls.is_java_runtime_failure(output),
        )

    @staticmethod
    def is_java_runtime_failure(output: str) -> bool:
        normalized = str(output or "").casefold()
        signatures = (
            "unsupportedclassversionerror",
            "compiled by a more recent version of the java runtime",
            "only recognizes class file versions up to",
            "a jni error has occurred",
            "could not create the java virtual machine",
            "error occurred during initialization of vm",
            "unrecognized vm option",
            "class file version",
        )
        return any(signature in normalized for signature in signatures)

    @staticmethod
    def _read_log(log_path: Path | None) -> str:
        if log_path is None:
            return ""
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @classmethod
    def log_path(cls, process: object) -> Path | None:
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return None
        with cls._process_logs_lock:
            record = cls._process_logs.get(pid)
        return record

    @classmethod
    def close_process_log(cls, process: object) -> None:
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int) or pid <= 0:
            return
        with cls._process_logs_lock:
            cls._process_logs.pop(pid, None)
