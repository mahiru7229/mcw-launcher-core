from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.instance.instance import Instance
from src.models.instance.instance_health import (
    InstanceHealthIssue,
    InstanceHealthReport,
    InstanceHealthSeverity,
    InstanceHealthState,
)


class InstanceHealthManager:
    """Run a fast, non-networked health check suitable for launcher startup."""

    _PRIORITY = {
        InstanceHealthState.HEALTHY: 0,
        InstanceHealthState.NEEDS_ATTENTION: 1,
        InstanceHealthState.MIGRATION_REQUIRED: 2,
        InstanceHealthState.MISSING_FILES: 3,
        InstanceHealthState.MISSING_JAVA: 4,
        InstanceHealthState.INCOMPLETE: 5,
        InstanceHealthState.CORRUPTED: 6,
    }

    @classmethod
    def scan(cls, instance: Instance) -> InstanceHealthReport:
        checked_at = datetime.now(timezone.utc).isoformat()
        issues: list[InstanceHealthIssue] = []
        instance_dir = Path(instance.instance_dir)
        metadata_path = instance_dir / "instance.json"
        settings_path = instance_dir / "settings.json"

        if not instance_dir.is_dir():
            issues.append(cls._issue("instance_directory_missing", InstanceHealthState.INCOMPLETE, InstanceHealthSeverity.ERROR, "The instance directory is missing.", instance_dir, False))
            return cls._report(instance, issues, checked_at)

        metadata = cls._load_json(metadata_path)
        if metadata is None:
            issues.append(cls._issue("metadata_missing", InstanceHealthState.INCOMPLETE, InstanceHealthSeverity.ERROR, "instance.json is missing.", metadata_path, False))
        elif metadata is False:
            issues.append(cls._issue("metadata_invalid", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, "instance.json is not valid JSON.", metadata_path, False))
        else:
            cls._check_metadata(instance, metadata, metadata_path, issues)

        settings = cls._load_json(settings_path)
        if settings is None:
            issues.append(cls._issue("settings_missing", InstanceHealthState.NEEDS_ATTENTION, InstanceHealthSeverity.WARNING, "settings.json is missing and will be recreated with defaults.", settings_path, True))
        elif settings is False or not isinstance(settings, dict):
            issues.append(cls._issue("settings_invalid", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, "settings.json is not valid.", settings_path, True))
        else:
            java_path = str(settings.get("java_path") or "").strip()
            if java_path and not Path(java_path).expanduser().is_file():
                issues.append(cls._issue("configured_java_missing", InstanceHealthState.MISSING_JAVA, InstanceHealthSeverity.ERROR, "The Java executable configured for this instance does not exist.", Path(java_path), True))

        cls._check_loader(instance, issues)
        cls._check_icon(instance, issues)
        cls._check_operation_journal(instance, issues)

        if bool(getattr(instance, "last_launch_crashed", False)):
            issues.append(cls._issue("last_launch_crashed", InstanceHealthState.NEEDS_ATTENTION, InstanceHealthSeverity.WARNING, "The previous Minecraft session ended in a crash.", None, True))

        return cls._report(instance, issues, checked_at)

    @classmethod
    def list(cls, instances: list[Instance]) -> list[InstanceHealthReport]:
        reports: list[InstanceHealthReport] = []
        for instance in instances:
            try:
                reports.append(cls.scan(instance))
            except Exception as error:
                reports.append(
                    InstanceHealthReport(
                        instance_id=str(getattr(instance, "instance_id", "") or ""),
                        name=str(getattr(instance, "name", "") or "Unknown"),
                        state=InstanceHealthState.CORRUPTED,
                        issues=(
                            InstanceHealthIssue(
                                code="health_scan_failed",
                                state=InstanceHealthState.CORRUPTED,
                                severity=InstanceHealthSeverity.ERROR,
                                message=f"Health scan failed: {type(error).__name__}: {error}",
                            ),
                        ),
                        checked_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
        return reports

    @classmethod
    def _check_metadata(cls, instance: Instance, metadata: dict, path: Path, issues: list[InstanceHealthIssue]) -> None:
        required = {"id", "name", "version_id", "mod_loader"}
        missing = sorted(key for key in required if not metadata.get(key))
        if missing:
            issues.append(cls._issue("metadata_required_fields_missing", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, f"instance.json is missing required fields: {', '.join(missing)}.", path, False))

        try:
            metadata_version = int(metadata.get("metadata_version", 1))
        except (TypeError, ValueError):
            issues.append(cls._issue("metadata_version_invalid", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, "The instance metadata version is invalid.", path, False))
        else:
            if metadata_version < InstanceManager.METADATA_VERSION:
                issues.append(cls._issue("metadata_migration_required", InstanceHealthState.MIGRATION_REQUIRED, InstanceHealthSeverity.WARNING, f"The instance uses metadata schema {metadata_version}; schema {InstanceManager.METADATA_VERSION} is available.", path, True))
            elif metadata_version > InstanceManager.METADATA_VERSION:
                issues.append(cls._issue("metadata_newer_than_launcher", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, f"The instance uses newer metadata schema {metadata_version}.", path, False))

        stored_name = str(metadata.get("name") or "").strip()
        if stored_name and stored_name != instance.name:
            issues.append(cls._issue("metadata_name_mismatch", InstanceHealthState.NEEDS_ATTENTION, InstanceHealthSeverity.WARNING, "The instance folder and metadata name do not match.", path, True))

    @classmethod
    def _check_loader(cls, instance: Instance, issues: list[InstanceHealthIssue]) -> None:
        try:
            loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        except Exception:
            issues.append(cls._issue("loader_invalid", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, "The mod-loader metadata is invalid.", Path(instance.instance_dir) / "instance.json", True))
            return
        supported = {ModLoaderManager.VANILLA, *ModLoaderManager.MODDED_LOADERS}
        if loader_name not in supported:
            issues.append(cls._issue("loader_unsupported", InstanceHealthState.CORRUPTED, InstanceHealthSeverity.ERROR, f"Unsupported mod loader: {loader_name}.", Path(instance.instance_dir) / "instance.json", True))
        elif loader_name != ModLoaderManager.VANILLA and loader_version in {"", "-1", ModLoaderManager.AUTO}:
            issues.append(cls._issue("loader_version_missing", InstanceHealthState.INCOMPLETE, InstanceHealthSeverity.ERROR, f"{loader_name.title()} does not have an installed loader version.", Path(instance.instance_dir) / "instance.json", True))

    @classmethod
    def _check_icon(cls, instance: Instance, issues: list[InstanceHealthIssue]) -> None:
        icon = str(getattr(instance, "icon", "") or "").strip()
        if not icon or icon == InstanceManager.DEFAULT_ICON:
            return
        path = Path(icon)
        if not path.is_absolute():
            path = Path(instance.instance_dir) / path
        if not path.is_file():
            issues.append(cls._issue("icon_missing", InstanceHealthState.NEEDS_ATTENTION, InstanceHealthSeverity.WARNING, "The custom instance icon is missing.", path, True))

    @classmethod
    def _check_operation_journal(cls, instance: Instance, issues: list[InstanceHealthIssue]) -> None:
        root = Paths.instance_operations_root()
        try:
            paths = tuple(root.glob("*.json"))
        except OSError:
            return
        instance_dir = Path(instance.instance_dir).resolve(strict=False)
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            names_match = str(payload.get("instance_name") or "") == instance.name
            paths_match = False
            for key in ("source_path", "target_path"):
                value = payload.get(key)
                if not value:
                    continue
                try:
                    paths_match = Path(str(value)).resolve(strict=False) == instance_dir
                except OSError:
                    paths_match = False
                if paths_match:
                    break
            if names_match or paths_match:
                operation = str(payload.get("operation") or "instance operation")
                phase = str(payload.get("phase") or "unknown")
                issues.append(cls._issue("operation_incomplete", InstanceHealthState.INCOMPLETE, InstanceHealthSeverity.ERROR, f"An unfinished {operation} operation remains in phase '{phase}'.", path, True))
                return

    @staticmethod
    def _load_json(path: Path) -> dict | list | bool | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return False

    @classmethod
    def _report(cls, instance: Instance, issues: list[InstanceHealthIssue], checked_at: str) -> InstanceHealthReport:
        state = max((issue.state for issue in issues), key=lambda item: cls._PRIORITY[item], default=InstanceHealthState.HEALTHY)
        return InstanceHealthReport(
            instance_id=str(getattr(instance, "instance_id", "") or ""),
            name=instance.name,
            state=state,
            issues=tuple(issues),
            checked_at=checked_at,
        )

    @staticmethod
    def _issue(code: str, state: InstanceHealthState, severity: InstanceHealthSeverity, message: str, path: Path | None, repairable: bool) -> InstanceHealthIssue:
        return InstanceHealthIssue(code=code, state=state, severity=severity, message=message, repairable=repairable, path=path)
