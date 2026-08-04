from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurseForgeManualDownload:
    project_id: int
    file_id: int
    project_name: str
    file_name: str
    file_size: int
    sha1: str
    project_url: str
    reason: str
    managed_kind: str = "mod"
    managed_path: str = ""
    direct_url: str = ""
    version_url: str = ""
    failure_reason: str = "UNKNOWN"
    http_status: int | None = None
    attempts: int = 1
    retryable: bool = False
    provider: str = "curseforge"
