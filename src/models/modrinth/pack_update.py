from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModrinthPackUpdateInfo:
    project_id: str
    pack_name: str
    current_version_id: str
    current_version_number: str
    target_version_id: str
    target_version_number: str
    target_version_type: str
    target_date_published: str

    @property
    def available(self) -> bool:
        return bool(self.target_version_id and self.target_version_id != self.current_version_id)


@dataclass(frozen=True, slots=True)
class ModrinthPackUpdateChange:
    path: str
    action: str
    reason: str = ""
    download_bytes: int = 0


@dataclass(frozen=True, slots=True)
class ModrinthPackUpdatePlan:
    instance_name: str
    pack_name: str
    current_version: str
    target_version: str
    target_version_id: str
    minecraft_version: str
    loader: str
    loader_version: str
    changes: tuple[ModrinthPackUpdateChange, ...]
    blockers: tuple[str, ...] = ()

    def count(self, action: str) -> int:
        normalized = str(action).strip().lower()
        return sum(1 for change in self.changes if change.action == normalized)

    @property
    def added_files(self) -> int:
        return self.count("add")

    @property
    def replaced_files(self) -> int:
        return self.count("replace")

    @property
    def removed_files(self) -> int:
        return self.count("remove")

    @property
    def preserved_files(self) -> tuple[str, ...]:
        return tuple(change.path for change in self.changes if change.action == "preserve")

    @property
    def unchanged_files(self) -> int:
        return self.count("unchanged")

    @property
    def estimated_download_bytes(self) -> int:
        return sum(max(0, change.download_bytes) for change in self.changes)

    @property
    def can_apply(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class ModrinthPackUpdateResult:
    instance_name: str
    pack_name: str
    previous_version: str
    target_version: str
    added_files: int
    replaced_files: int
    removed_files: int
    preserved_files: tuple[str, ...]
    backup_path: Path
    unchanged_files: int = 0
