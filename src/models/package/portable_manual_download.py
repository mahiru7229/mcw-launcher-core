from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PortableManualDownload:
    provider: str
    project_id: str
    file_id: str
    project_name: str
    file_name: str
    file_size: int
    sha1: str
    sha512: str
    project_url: str
    reason: str
    managed_path: str
    version_id: str = ""
    version_url: str = ""
    direct_url: str = ""
    managed_kind: str = "mod"
