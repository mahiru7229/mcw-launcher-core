from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModrinthModUpdateEntry:
    project_id: str
    title: str
    file_name: str
    current_version_id: str
    current_version_number: str
    latest_version_id: str
    latest_version_number: str
    latest_version_type: str
    locked: bool = False
    file_missing: bool = False
    warning: str = ""

    @property
    def update_available(self) -> bool:
        return bool(self.latest_version_id and self.latest_version_id != self.current_version_id)

    @property
    def status(self) -> str:
        if self.file_missing:
            return "Missing file"
        if self.warning:
            return "Check failed"
        if self.locked and self.update_available:
            return "Update locked"
        if self.update_available:
            return "Update available"
        return "Up to date"


@dataclass(frozen=True, slots=True)
class ModrinthModUpdateReport:
    entries: tuple[ModrinthModUpdateEntry, ...]

    @property
    def update_count(self) -> int:
        return sum(1 for entry in self.entries if entry.update_available and not entry.locked and not entry.file_missing and not entry.warning)

    @property
    def locked_count(self) -> int:
        return sum(1 for entry in self.entries if entry.locked)


@dataclass(frozen=True, slots=True)
class ModrinthModUpdateResult:
    updated_projects: tuple[str, ...]
    updated_files: tuple[str, ...]
    skipped_locked: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
