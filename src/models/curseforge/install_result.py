from __future__ import annotations

from dataclasses import dataclass

from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.instance.instance import Instance


@dataclass(frozen=True, slots=True)
class CurseForgeModInstallResult:
    installed_projects: tuple[str, ...]
    installed_files: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    manual_downloads: tuple[CurseForgeManualDownload, ...] = ()
    instance_name: str = ""


@dataclass(frozen=True, slots=True)
class CurseForgeModpackInstallResult:
    instance: Instance
    pack_name: str
    pack_version: str
    managed_files: int
    skipped_optional_files: int
