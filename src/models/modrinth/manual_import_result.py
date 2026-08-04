from __future__ import annotations

from dataclasses import dataclass

from src.models.modrinth.manual_download import ModrinthManualDownload


@dataclass(frozen=True, slots=True)
class ModrinthManualImportedFile:
    requirement: ModrinthManualDownload
    installed_name: str


@dataclass(frozen=True, slots=True)
class ModrinthManualImportResult:
    imported: tuple[ModrinthManualImportedFile, ...] = ()
    added_mods: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
