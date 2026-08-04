from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModrinthManagedFileChange:
    path: str
    state: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class ModrinthPackStateReport:
    project_id: str
    version_id: str
    managed_files: int
    changes: tuple[ModrinthManagedFileChange, ...]
    verified_files: int = 0
    cache_hits: int = 0
    hashed_files: int = 0

    @property
    def modified_count(self) -> int:
        return sum(1 for change in self.changes if change.state == "modified")

    @property
    def missing_count(self) -> int:
        return sum(1 for change in self.changes if change.state == "missing")
