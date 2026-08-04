from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any
import zipfile

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_health_manager import InstanceHealthManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.network.download_recovery import download_recovery_manager
from src.core.runtime.process_supervisor import ProcessSupervisor
from src.core.security.sensitive_data_redactor import SensitiveDataRedactor


class DiagnosticsManager:
    REPORT_SCHEMA_VERSION = 1
    BUNDLE_SCHEMA_VERSION = 1
    MAX_LOG_FILES = 8
    MAX_LOG_BYTES = 256 * 1024
    MAX_TOTAL_LOG_BYTES = 2 * 1024 * 1024

    @classmethod
    def build_report(cls, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = "") -> str:
        active_instances = InstanceRunLock.list_active()
        try:
            instances = InstanceManager.list_instances()
        except Exception as error:
            instances = []
            instance_error = SensitiveDataRedactor.redact_text(error)
        else:
            instance_error = ""

        try:
            health_reports = InstanceHealthManager.list(instances)
        except Exception:
            health_reports = []
        try:
            process_sessions = ProcessSupervisor.list_active()
        except Exception:
            process_sessions = ()

        safe_settings = cls._safe_settings(settings or {})
        language_files = cls._language_files()
        lines = [
            "MCW Launcher Diagnostic Report",
            "=" * 30,
            f"schema_version: {cls.REPORT_SCHEMA_VERSION}",
            f"generated_at: {datetime.now(timezone.utc).isoformat()}",
            f"launcher_version: {launcher_version}",
            f"packaged: {bool(getattr(sys, 'frozen', False))}",
            f"python: {platform.python_version()}",
            f"platform: {platform.platform()}",
            f"architecture: {platform.machine() or 'unknown'}",
            f"executable: {Path(sys.executable).resolve()}",
            f"working_directory: {Path.cwd().resolve()}",
            f"application_root: {Paths.root().resolve()}",
            "",
            "Data directories",
            "----------------",
            f"config: {Paths.CONFIG_ROOT.resolve()}",
            f"instances: {Paths.INSTANCES_ROOT.resolve()}",
            f"cache: {Paths.CACHE_ROOT.resolve()}",
            f"accounts: {Paths.ACCOUNTS_ROOT.resolve()}",
            f"logs: {Paths.LOGS_ROOT.resolve()}",
            "",
            "Runtime state",
            "-------------",
            f"instance_count: {len(instances)}",
            f"running_instance_count: {len(active_instances)}",
            f"supervised_session_count: {len(process_sessions)}",
            f"healthy_instance_count: {sum(1 for report in health_reports if report.healthy)}",
            f"attention_instance_count: {sum(1 for report in health_reports if not report.healthy)}",
        ]
        if instance_error:
            lines.append(f"instance_scan_error: {instance_error}")
        for item in active_instances:
            lines.append(f"running_instance: {item.name} [{item.state}] pid={item.minecraft_pid or item.launcher_pid or 'unknown'}")
        for report in health_reports:
            if not report.healthy:
                lines.append(f"instance_health: {report.name} [{report.state.value}] issues={len(report.issues)}")

        lines.extend([
            "",
            "Language packs",
            "--------------",
            *(language_files or ["none detected"]),
            "",
            "Launcher settings (safe subset)",
            "-------------------------------",
            json.dumps(safe_settings, ensure_ascii=False, indent=2, sort_keys=True),
        ])

        if activity_log.strip():
            safe_activity = SensitiveDataRedactor.redact_text(activity_log.strip())
            lines.extend(["", "Recent frontend activity", "------------------------", safe_activity])

        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def write_report(cls, path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = "") -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.tmp")
        payload = cls.build_report(launcher_version=launcher_version, settings=settings, activity_log=activity_log)
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(destination)
        return destination

    @classmethod
    def write_bundle(cls, path: Path, launcher_version: str, settings: dict[str, Any] | None = None, activity_log: str = "") -> Path:
        destination = Path(path)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")

        entries: dict[str, bytes] = {
            "report.txt": cls.build_report(
                launcher_version=launcher_version,
                settings=settings,
                activity_log=activity_log,
            ).encode("utf-8"),
            "download-recovery.json": cls._download_recovery_json(),
            "instance-health.json": cls._instance_health_json(),
            "process-sessions.json": cls._process_sessions_json(),
            "operation-journals.json": cls._operation_journals_json(),
        }
        entries.update(cls._safe_log_entries())
        manifest_entries = [
            {
                "path": name,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in sorted(entries.items())
        ]
        entries["manifest.json"] = (
            json.dumps(
                {
                    "schema_version": cls.BUNDLE_SCHEMA_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "launcher_version": str(launcher_version),
                    "entries": manifest_entries,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name, payload in sorted(entries.items()):
                    archive.writestr(name, payload)
            with temporary.open("r+b") as file:
                file.flush()
                os.fsync(file.fileno())
            with zipfile.ZipFile(temporary, "r") as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("The diagnostic bundle failed integrity verification.")
                cls._validate_bundle_names(archive.namelist())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    @classmethod
    def _download_recovery_json(cls) -> bytes:
        try:
            report = download_recovery_manager.inspect()
            items = [
                {
                    "request_id": item.request_id,
                    "display_name": SensitiveDataRedactor.redact_text(item.display_name),
                    "destination": cls._safe_path(item.destination),
                    "state": item.state.value,
                    "downloaded_bytes": item.downloaded_bytes,
                    "expected_size": item.expected_size,
                    "reason": item.reason,
                }
                for item in report.items
            ]
            payload: dict[str, Any] = {
                "schema_version": 1,
                "resumable_count": report.resumable_count,
                "items": items,
            }
        except Exception as error:
            payload = {
                "schema_version": 1,
                "error": SensitiveDataRedactor.redact_text(error),
                "items": [],
            }
        return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @classmethod
    def _instance_health_json(cls) -> bytes:
        try:
            reports = InstanceHealthManager.list(InstanceManager.list_instances())
            instances: list[dict[str, Any]] = []
            for report in reports:
                data = report.to_dict()
                for issue in data.get("issues", []):
                    path = issue.get("path")
                    if path:
                        issue["path"] = cls._safe_path(Path(str(path)))
                instances.append(SensitiveDataRedactor.redact_value(data))
            payload: dict[str, Any] = {
                "schema_version": 1,
                "instances": instances,
            }
        except Exception as error:
            payload = {"schema_version": 1, "error": SensitiveDataRedactor.redact_text(error), "instances": []}
        return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @classmethod
    def _process_sessions_json(cls) -> bytes:
        try:
            sessions = ProcessSupervisor.list_active()
            rows = []
            for session in sessions:
                data = session.to_dict()
                data["instance_dir"] = cls._safe_path(session.instance_dir)
                rows.append(SensitiveDataRedactor.redact_value(data))
            payload: dict[str, Any] = {"schema_version": 1, "sessions": rows}
        except Exception as error:
            payload = {"schema_version": 1, "error": SensitiveDataRedactor.redact_text(error), "sessions": []}
        return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @classmethod
    def _operation_journals_json(cls) -> bytes:
        rows: list[dict[str, Any]] = []
        try:
            paths = tuple(Paths.instance_operations_root().glob("*.json"))
        except OSError:
            paths = ()
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                rows.append({"journal": path.name, "state": "invalid"})
                continue
            if not isinstance(payload, dict):
                rows.append({"journal": path.name, "state": "invalid"})
                continue
            safe = {
                "journal": path.name,
                "operation_id": str(payload.get("operation_id") or ""),
                "operation": str(payload.get("operation") or ""),
                "instance_name": str(payload.get("instance_name") or ""),
                "phase": str(payload.get("phase") or ""),
                "created_at": str(payload.get("created_at") or ""),
                "updated_at": str(payload.get("updated_at") or ""),
            }
            for key in ("source_path", "target_path", "staging_path"):
                value = payload.get(key)
                if value:
                    safe[key] = cls._safe_path(Path(str(value)))
            rows.append(SensitiveDataRedactor.redact_value(safe))
        payload = {"schema_version": 1, "journals": rows}
        return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @classmethod
    def _safe_log_entries(cls) -> dict[str, bytes]:
        root = Paths.LOGS_ROOT
        try:
            candidates = [
                path
                for path in root.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and path.suffix.casefold() in {".log", ".txt"}
            ]
        except OSError:
            return {}

        def modified(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        entries: dict[str, bytes] = {}
        total = 0
        for path in sorted(candidates, key=modified, reverse=True):
            if len(entries) >= cls.MAX_LOG_FILES or total >= cls.MAX_TOTAL_LOG_BYTES:
                break
            remaining = cls.MAX_TOTAL_LOG_BYTES - total
            limit = min(cls.MAX_LOG_BYTES, remaining)
            try:
                with path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    size = stream.tell()
                    stream.seek(max(0, size - limit))
                    raw = stream.read(limit)
            except OSError:
                continue
            text = raw.decode("utf-8", errors="replace")
            if size > len(raw):
                text = "[log tail truncated]\n" + text
            safe = cls._truncate_utf8(
                SensitiveDataRedactor.redact_text(text).encode("utf-8"),
                limit,
            )
            name = cls._safe_log_name(len(entries) + 1, path.name)
            entries[name] = safe
            total += len(safe)
        return entries

    @staticmethod
    def _safe_log_name(index: int, filename: str) -> str:
        safe_name = "".join(
            character if character.isalnum() or character in {"-", "_", "."} else "_"
            for character in Path(filename).name
        ).strip(" .")
        return f"logs/{index:02d}-{safe_name or 'launcher.log'}"

    @staticmethod
    def _truncate_utf8(payload: bytes, limit: int) -> bytes:
        if len(payload) <= max(0, limit):
            return payload
        return payload[:max(0, limit)].decode("utf-8", errors="ignore").encode("utf-8")

    @staticmethod
    def _validate_bundle_names(names: list[str]) -> None:
        for name in names:
            path = Path(str(name).replace("\\", "/"))
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise RuntimeError(f"Unsafe path in diagnostic bundle: {name!r}")

    @staticmethod
    def _safe_path(path: Path) -> str:
        candidate = Path(path)
        try:
            resolved = candidate.resolve(strict=False)
            root = Paths.root().resolve(strict=False)
            relative = resolved.relative_to(root)
        except (OSError, ValueError):
            return f"<external>/{candidate.name or 'download'}"
        return relative.as_posix()

    @staticmethod
    def _safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
        allowed_sections = {"gui", "launch", "updates", "window"}
        safe: dict[str, Any] = {}
        for section, value in settings.items():
            if section not in allowed_sections or not isinstance(value, dict):
                continue
            safe[section] = SensitiveDataRedactor.redact_value(dict(value))
        geometry = safe.get("window", {}).get("geometry")
        if geometry:
            safe["window"]["geometry"] = "<saved>"
        return safe

    @staticmethod
    def _language_files() -> list[str]:
        roots = [Paths.root() / "lang"]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass) / "lang")
        found: set[str] = set()
        for root in roots:
            try:
                found.update(path.name for path in root.glob("*.json") if path.is_file())
            except OSError:
                continue
        return sorted(found, key=str.casefold)
