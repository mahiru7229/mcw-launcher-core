from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModrinthManualDownload:
    project_id: str
    version_id: str
    project_name: str
    file_name: str
    file_size: int
    sha1: str
    sha512: str
    project_url: str
    version_url: str
    direct_url: str
    reason: str
    failure_reason: str = "UNKNOWN"
    http_status: int | None = None
    attempts: int = 1
    retryable: bool = False
    managed_kind: str = "mod"
    managed_path: str = ""
    provider: str = "modrinth"

    @property
    def file_id(self) -> str:
        return self.version_id
