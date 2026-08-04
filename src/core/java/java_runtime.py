from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO

from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.paths import Paths
from src.core.hardware.gpu_preference_manager import GpuPreferenceManager
from src.core.java.java_command_compactor import JavaCommandCompactor
from src.models.instance.instance import Instance


class JavaRuntime:
    _process_logs: dict[int, Path] = {}
    _process_logs_lock = threading.RLock()

    @classmethod
    def run(cls, java: Path, command: list[str], instance: Instance) -> subprocess.Popen:
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        log_dir = Paths.instance_logs_dir(instance)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = log_dir / f"minecraft-{timestamp}.log"
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
    def _popen(java: Path, command: list[str], instance_dir: Path, log_file: TextIO, creation_flags: int) -> subprocess.Popen:
        return subprocess.Popen(
            [str(java), *command],
            cwd=instance_dir,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )

    @staticmethod
    def _is_windows_length_error(error: OSError) -> bool:
        return os.name == "nt" and getattr(error, "winerror", None) == 206

    @staticmethod
    def _windows_length_error(instance_dir: Path) -> RuntimeError:
        return RuntimeError(
            "Windows could not start Minecraft because the launch command or one of its paths is still too long. "
            f"Move MCW Launcher to a shorter folder such as C:\\MCW and shorten the instance name if needed. Instance: {instance_dir}"
        )

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
