from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class InstanceHealthState(StrEnum):
    HEALTHY = "healthy"
    NEEDS_ATTENTION = "needs_attention"
    MIGRATION_REQUIRED = "migration_required"
    MISSING_JAVA = "missing_java"
    MISSING_FILES = "missing_files"
    INCOMPLETE = "incomplete"
    CORRUPTED = "corrupted"


class InstanceHealthSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class InstanceHealthIssue:
    code: str
    state: InstanceHealthState
    severity: InstanceHealthSeverity
    message: str
    repairable: bool = False
    path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "state": self.state.value,
            "severity": self.severity.value,
            "message": self.message,
            "repairable": self.repairable,
            "path": str(self.path) if self.path is not None else None,
        }


@dataclass(frozen=True, slots=True)
class InstanceHealthReport:
    instance_id: str
    name: str
    state: InstanceHealthState
    issues: tuple[InstanceHealthIssue, ...]
    checked_at: str

    @property
    def healthy(self) -> bool:
        return self.state is InstanceHealthState.HEALTHY

    @property
    def repairable(self) -> bool:
        return any(issue.repairable for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "state": self.state.value,
            "healthy": self.healthy,
            "repairable": self.repairable,
            "checked_at": self.checked_at,
            "issues": [issue.to_dict() for issue in self.issues],
        }
