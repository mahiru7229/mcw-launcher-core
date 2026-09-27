from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ScreenshotInfo:
    """Metadata representing an in-game screenshot."""

    path: Path
    file_name: str
    file_size_bytes: int = 0
    created_timestamp: float = 0.0

    @property
    def filename(self) -> str:
        return self.file_name
