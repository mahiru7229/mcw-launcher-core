from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping


class DownloadFailureReason(str, Enum):
    NO_DOWNLOAD_URL = "NO_DOWNLOAD_URL"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    READ_TIMEOUT = "READ_TIMEOUT"
    DNS_ERROR = "DNS_ERROR"
    TLS_ERROR = "TLS_ERROR"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_5XX = "HTTP_5XX"
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    CONNECTION_RESET = "CONNECTION_RESET"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    HASH_MISMATCH = "HASH_MISMATCH"
    FILE_ACCESS_ERROR = "FILE_ACCESS_ERROR"
    DISK_SPACE_ERROR = "DISK_SPACE_ERROR"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ArtifactRequest:
    provider: str
    purpose: str
    destination: Path
    urls: tuple[str, ...] = ()
    page_url: str = ""
    project_url: str = ""
    expected_filename: str = ""
    expected_size: int = 0
    hashes: Mapping[str, str] = field(default_factory=dict)
    project_id: str = ""
    version_id: str = ""
    file_id: str = ""
    max_attempts: int = 3
    timeout: float | object = 30.0
    headers: Mapping[str, str] = field(default_factory=dict)
    force: bool = False
    allow_unverified: bool = False
    max_bytes: int = 0
    operation_id: str = ""

    def __post_init__(self) -> None:
        destination = Path(self.destination)
        normalized_urls = tuple(dict.fromkeys(str(url).strip() for url in self.urls if str(url).strip()))
        normalized_hashes = {
            str(algorithm).strip().lower(): str(value).strip().lower()
            for algorithm, value in dict(self.hashes or {}).items()
            if str(algorithm).strip() and str(value).strip()
        }
        object.__setattr__(self, "provider", str(self.provider or "generic").strip().lower() or "generic")
        object.__setattr__(self, "purpose", str(self.purpose or "artifact").strip().lower() or "artifact")
        object.__setattr__(self, "destination", destination)
        object.__setattr__(self, "urls", normalized_urls)
        object.__setattr__(self, "page_url", str(self.page_url or "").strip())
        object.__setattr__(self, "project_url", str(self.project_url or "").strip())
        object.__setattr__(self, "expected_filename", Path(str(self.expected_filename or destination.name)).name)
        object.__setattr__(self, "expected_size", max(0, int(self.expected_size or 0)))
        object.__setattr__(self, "hashes", normalized_hashes)
        object.__setattr__(self, "project_id", str(self.project_id or "").strip())
        object.__setattr__(self, "version_id", str(self.version_id or "").strip())
        object.__setattr__(self, "file_id", str(self.file_id or "").strip())
        object.__setattr__(self, "max_attempts", max(1, int(self.max_attempts or 1)))
        object.__setattr__(self, "max_bytes", max(0, int(self.max_bytes or 0)))
        object.__setattr__(self, "operation_id", str(self.operation_id or "").strip())

    @property
    def direct_url(self) -> str:
        return self.urls[0] if self.urls else ""


@dataclass(frozen=True, slots=True)
class ArtifactDownloadFailure:
    provider: str
    filename: str
    reason: DownloadFailureReason
    detail: str
    url: str = ""
    page_url: str = ""
    project_url: str = ""
    http_status: int | None = None
    attempts: int = 1
    retryable: bool = False
    project_id: str = ""
    version_id: str = ""
    file_id: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "filename": self.filename,
            "reason": self.reason.value,
            "detail": self.detail,
            "url": self.url,
            "pageUrl": self.page_url,
            "projectUrl": self.project_url,
            "httpStatus": self.http_status,
            "attempts": self.attempts,
            "retryable": self.retryable,
            "projectId": self.project_id,
            "versionId": self.version_id,
            "fileId": self.file_id,
        }
