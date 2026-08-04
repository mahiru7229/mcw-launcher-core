from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModrinthPackRepairResult:
    instance_name: str
    pack_name: str
    pack_version: str
    restored_files: tuple[str, ...]
    missing_files: int
    modified_files: int
    healthy_files: int
    backup_path: Path | None = None

    @property
    def repaired_files(self) -> int:
        return len(self.restored_files)
