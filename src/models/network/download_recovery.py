from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DownloadRecoveryState(str, Enum):
    RESUMABLE = "resumable"
    READY_TO_VERIFY = "ready_to_verify"
    COMPLETED = "completed"
    STALE = "stale"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DownloadRecoveryItem:
    request_id: str
    display_name: str
    destination: Path
    temporary_path: Path
    state: DownloadRecoveryState
    downloaded_bytes: int
    expected_size: int
    reason: str = ""

    @property
    def keeps_partial(self) -> bool:
        return self.state in {
            DownloadRecoveryState.RESUMABLE,
            DownloadRecoveryState.READY_TO_VERIFY,
        }


@dataclass(frozen=True, slots=True)
class DownloadRecoveryReport:
    items: tuple[DownloadRecoveryItem, ...]
    removed_journal_entries: int = 0
    deleted_partial_files: int = 0
    deleted_partial_bytes: int = 0

    def count(self, state: DownloadRecoveryState) -> int:
        return sum(1 for item in self.items if item.state is state)

    @property
    def resumable_count(self) -> int:
        return sum(1 for item in self.items if item.keeps_partial)

    @property
    def cleaned_count(self) -> int:
        return self.removed_journal_entries
