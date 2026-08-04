from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.fs.paths import Paths


@dataclass(frozen=True, slots=True)
class InstanceRecoveryRecord:
    operation_id: str
    operation: str
    result: str
    instance_name: str


@dataclass(slots=True)
class InstanceOperationJournal:
    operation_id: str
    operation: str
    instance_name: str
    path: Path
    payload: dict[str, Any]

    SCHEMA_VERSION = 1

    @classmethod
    def begin(
        cls,
        operation: str,
        instance_name: str,
        *,
        source_path: Path | None = None,
        target_path: Path | None = None,
        staging_path: Path | None = None,
    ) -> InstanceOperationJournal:
        operation_id = uuid.uuid4().hex
        now = cls._utc_now()
        payload = {
            "schema_version": cls.SCHEMA_VERSION,
            "operation_id": operation_id,
            "operation": str(operation),
            "instance_name": str(instance_name),
            "phase": "preparing",
            "source_path": str(source_path) if source_path is not None else None,
            "target_path": str(target_path) if target_path is not None else None,
            "staging_path": str(staging_path) if staging_path is not None else None,
            "created_at": now,
            "updated_at": now,
        }
        path = Paths.instance_operations_root() / f"{operation_id}.json"
        journal = cls(operation_id=operation_id, operation=str(operation), instance_name=str(instance_name), path=path, payload=payload)
        journal._write()
        return journal

    def update(self, phase: str, **updates: Any) -> None:
        self.payload.update(updates)
        self.payload["phase"] = str(phase)
        self.payload["updated_at"] = self._utc_now()
        self._write()

    def complete(self) -> None:
        self.path.unlink(missing_ok=True)

    def abandon(self) -> None:
        self.path.unlink(missing_ok=True)

    @classmethod
    def recover_all(cls) -> tuple[InstanceRecoveryRecord, ...]:
        root = Paths.instance_operations_root()
        records: list[InstanceRecoveryRecord] = []
        for path in sorted(root.glob("*.json")):
            record = cls._recover_path(path)
            if record is not None:
                records.append(record)
        return tuple(records)

    @classmethod
    def _recover_path(cls, path: Path) -> InstanceRecoveryRecord | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            path.unlink(missing_ok=True)
            return InstanceRecoveryRecord(path.stem, "unknown", "discarded-invalid-journal", "")

        if not isinstance(payload, dict):
            path.unlink(missing_ok=True)
            return InstanceRecoveryRecord(path.stem, "unknown", "discarded-invalid-journal", "")

        operation_id = str(payload.get("operation_id") or path.stem)
        operation = str(payload.get("operation") or "unknown")
        instance_name = str(payload.get("instance_name") or "")
        phase = str(payload.get("phase") or "preparing")
        source = cls._safe_instance_path(payload.get("source_path"))
        target = cls._safe_instance_path(payload.get("target_path"))
        staging = cls._safe_staging_path(payload.get("staging_path"))

        if operation in {"create", "clone", "import"}:
            if target is not None and target.is_dir() and (target / "instance.json").is_file():
                if staging is not None and staging.exists():
                    cls._remove_path(staging)
                path.unlink(missing_ok=True)
                return InstanceRecoveryRecord(operation_id, operation, "committed", instance_name)
            if staging is not None and staging.exists():
                cls._remove_path(staging)
            path.unlink(missing_ok=True)
            return InstanceRecoveryRecord(operation_id, operation, "rolled-back", instance_name)

        if operation == "rename":
            if target is not None and target.is_dir() and (target / "instance.json").is_file() and (source is None or not source.exists()):
                path.unlink(missing_ok=True)
                return InstanceRecoveryRecord(operation_id, operation, "committed", instance_name)
            if source is not None and source.is_dir() and (target is None or not target.exists()):
                path.unlink(missing_ok=True)
                return InstanceRecoveryRecord(operation_id, operation, "rolled-back", instance_name)
            if phase == "preparing":
                path.unlink(missing_ok=True)
                return InstanceRecoveryRecord(operation_id, operation, "rolled-back", instance_name)
            return InstanceRecoveryRecord(operation_id, operation, "manual-recovery-required", instance_name)

        if staging is not None and staging.exists():
            cls._remove_path(staging)
        path.unlink(missing_ok=True)
        return InstanceRecoveryRecord(operation_id, operation, "discarded-unknown-operation", instance_name)

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _safe_instance_path(value: object) -> Path | None:
        if not value:
            return None
        return InstanceOperationJournal._safe_path(Path(str(value)), Paths.instances_root())

    @staticmethod
    def _safe_staging_path(value: object) -> Path | None:
        if not value:
            return None
        return InstanceOperationJournal._safe_path(Path(str(value)), Paths.instance_staging_root())

    @staticmethod
    def _safe_path(path: Path, allowed_root: Path) -> Path | None:
        candidate = path.expanduser().resolve(strict=False)
        root = allowed_root.resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(self.payload, indent=2, ensure_ascii=False) + "\n")
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(self.path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
