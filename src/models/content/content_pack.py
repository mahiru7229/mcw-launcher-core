from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentPackEntry:
    entry_id: str
    content_type: str
    provider: str
    project_id: str
    version_id: str
    file_id: str
    project_name: str
    version_number: str
    pack_format: int | None
    pack_description: str
    file_name: str
    target_path: str
    sha1: str
    sha512: str
    size: int
    source_url: str
    project_url: str
    installed_at: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ContentPackInstallResult:
    instance_name: str
    content_type: str
    provider: str
    project_name: str
    file_name: str
    target_path: str
    replaced: bool = False
