from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping
from uuid import uuid4


class DownloadState(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    MANUAL_ACTION_REQUIRED = "manual_action_required"


@dataclass(frozen=True)
class DownloadRequest:
    urls: tuple[str, ...]
    destination: Path
    expected_size: int = 0
    hashes: Mapping[str, str] = field(default_factory=dict)
    source: str = "generic"
    display_name: str = ""
    max_attempts: int = 3
    timeout: float | object = 30.0
    headers: Mapping[str, str] = field(default_factory=dict)
    force: bool = False
    allow_unverified: bool = False
    max_bytes: int = 0
    operation_id: str = ""
    request_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        normalized_urls = tuple(dict.fromkeys(str(url).strip() for url in self.urls if str(url).strip()))
        object.__setattr__(self, "urls", normalized_urls)
        object.__setattr__(self, "destination", Path(self.destination))
        object.__setattr__(self, "expected_size", max(0, int(self.expected_size or 0)))
        object.__setattr__(self, "max_attempts", max(1, int(self.max_attempts or 1)))
        object.__setattr__(self, "max_bytes", max(0, int(self.max_bytes or 0)))
        normalized_hashes = {
            str(algorithm).strip().lower(): str(value).strip().lower()
            for algorithm, value in dict(self.hashes or {}).items()
            if str(algorithm).strip() and str(value).strip()
        }
        object.__setattr__(self, "hashes", normalized_hashes)
        object.__setattr__(self, "source", str(self.source or "generic").strip() or "generic")
        object.__setattr__(self, "display_name", str(self.display_name or self.destination.name).strip() or self.destination.name)
        object.__setattr__(self, "operation_id", str(self.operation_id or "").strip())

    @property
    def temporary_path(self) -> Path:
        return self.destination.with_name(f"{self.destination.name}.part")


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    size: int
    hashes: Mapping[str, str]
    resumed_from: int = 0
    source_url: str = ""
