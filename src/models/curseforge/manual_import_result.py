from __future__ import annotations

from dataclasses import dataclass

from src.models.curseforge.manual_download import CurseForgeManualDownload


@dataclass(frozen=True, slots=True)
class CurseForgeManualImportedFile:
    requirement: CurseForgeManualDownload
    installed_name: str


@dataclass(frozen=True, slots=True)
class CurseForgeManualImportResult:
    imported: tuple[CurseForgeManualImportedFile, ...] = ()
    added_mods: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
