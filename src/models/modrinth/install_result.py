from __future__ import annotations

from dataclasses import dataclass

from src.models.instance.instance import Instance
from src.models.modrinth.manual_download import ModrinthManualDownload


@dataclass(frozen=True, slots=True)
class ModrinthModInstallResult:
    installed_projects: tuple[str, ...]
    installed_files: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    manual_downloads: tuple[ModrinthManualDownload, ...] = ()
    instance_name: str = ""


@dataclass(frozen=True, slots=True)
class ModrinthModpackInstallResult:
    instance: Instance
    pack_name: str
    pack_version: str
    installed_files: int
    skipped_optional_files: int
    skipped_server_files: int
