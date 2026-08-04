from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstanceBackupInfo:
    path: Path
    instance_id: str
    instance_name: str
    scope: str
    created_at: str
    file_count: int
    total_size: int
    launcher_version: str
    reason: str = "manual"


@dataclass(frozen=True, slots=True)
class InstanceBackupResult:
    backup: InstanceBackupInfo


@dataclass(frozen=True, slots=True)
class InstanceRestoreResult:
    instance_name: str
    backup_path: Path
    restored_files: int
    scope: str
    safety_backup: Path | None = None
