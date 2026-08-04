from __future__ import annotations

from dataclasses import dataclass

from src.models.instance.instance import Instance


@dataclass(frozen=True, slots=True)
class FTBModpackInstallResult:
    instance: Instance
    pack_name: str
    pack_version: str
    managed_files: int
    skipped_optional_files: int
    skipped_server_files: int
