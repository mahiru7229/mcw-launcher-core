from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class RepairMode(str, Enum):
    QUICK = "quick"
    FULL = "full"


class RepairComponent(str, Enum):
    CLIENT = "client"
    LIBRARIES = "libraries"
    ASSETS = "assets"
    JAVA = "java"
    MOD_LOADER = "mod_loader"
    MODPACK = "modpack"
    LAN_AGENT = "lan_agent"
    SETTINGS = "settings"


class RepairSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RepairStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    HEALTHY = "healthy"
    WARNING = "warning"
    BROKEN = "broken"
    REPAIRED = "repaired"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RepairIssue:
    component: RepairComponent
    code: str
    message: str
    severity: RepairSeverity
    repairable: bool
    path: Path | None = None
    expected_hash: str = ""
    expected_size: int = 0
    download_bytes: int = 0
    manual_action: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["component"] = self.component.value
        data["severity"] = self.severity.value
        data["path"] = str(self.path) if self.path is not None else None
        return data


@dataclass(frozen=True, slots=True)
class RepairComponentResult:
    component: RepairComponent
    status: RepairStatus
    checked_files: int = 0
    cache_hits: int = 0
    hashed_files: int = 0
    issues: tuple[RepairIssue, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "component": self.component.value,
            "status": self.status.value,
            "checked_files": self.checked_files,
            "cache_hits": self.cache_hits,
            "hashed_files": self.hashed_files,
            "issues": [issue.to_dict() for issue in self.issues],
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RepairReport:
    instance_name: str
    mode: RepairMode
    components: tuple[RepairComponentResult, ...]
    started_at: str
    completed_at: str

    @property
    def issues(self) -> tuple[RepairIssue, ...]:
        return tuple(issue for component in self.components for issue in component.issues)

    @property
    def checked_files(self) -> int:
        return sum(component.checked_files for component in self.components)

    @property
    def cache_hits(self) -> int:
        return sum(component.cache_hits for component in self.components)

    @property
    def hashed_files(self) -> int:
        return sum(component.hashed_files for component in self.components)

    @property
    def healthy(self) -> bool:
        return not any(issue.severity is RepairSeverity.ERROR for issue in self.issues)

    def component(self, component: RepairComponent) -> RepairComponentResult | None:
        return next((item for item in self.components if item.component is component), None)

    def to_dict(self) -> dict:
        return {
            "instance_name": self.instance_name,
            "mode": self.mode.value,
            "components": [component.to_dict() for component in self.components],
            "checked_files": self.checked_files,
            "cache_hits": self.cache_hits,
            "hashed_files": self.hashed_files,
            "healthy": self.healthy,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True, slots=True)
class RepairPlan:
    instance_name: str
    report: RepairReport
    selected_components: tuple[RepairComponent, ...]
    issues: tuple[RepairIssue, ...]
    estimated_download_bytes: int
    requires_manual_action: bool

    @property
    def repairable_issues(self) -> tuple[RepairIssue, ...]:
        return tuple(issue for issue in self.issues if issue.repairable)

    @property
    def can_repair(self) -> bool:
        return bool(self.repairable_issues)

    @property
    def requires_safety_backup(self) -> bool:
        instance_components = {
            RepairComponent.MOD_LOADER,
            RepairComponent.MODPACK,
            RepairComponent.SETTINGS,
        }
        return any(issue.repairable and issue.component in instance_components for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "instance_name": self.instance_name,
            "selected_components": [component.value for component in self.selected_components],
            "issues": [issue.to_dict() for issue in self.issues],
            "estimated_download_bytes": self.estimated_download_bytes,
            "requires_manual_action": self.requires_manual_action,
            "requires_safety_backup": self.requires_safety_backup,
        }


@dataclass(frozen=True, slots=True)
class RepairExecutionResult:
    instance_name: str
    selected_components: tuple[RepairComponent, ...]
    repaired_components: tuple[RepairComponent, ...]
    failed_components: tuple[RepairComponent, ...]
    warnings: tuple[str, ...]
    checked_files: int
    repaired_issues: int
    completed_at: str
    report_path: Path
    backup_path: Path | None = None
    rolled_back: bool = False
    rollback_error: str = ""

    @property
    def succeeded(self) -> bool:
        return not self.failed_components

    def to_dict(self) -> dict:
        return {
            "instance_name": self.instance_name,
            "selected_components": [component.value for component in self.selected_components],
            "repaired_components": [component.value for component in self.repaired_components],
            "failed_components": [component.value for component in self.failed_components],
            "warnings": list(self.warnings),
            "checked_files": self.checked_files,
            "repaired_issues": self.repaired_issues,
            "completed_at": self.completed_at,
            "report_path": str(self.report_path),
            "backup_path": str(self.backup_path) if self.backup_path is not None else None,
            "rolled_back": self.rolled_back,
            "rollback_error": self.rollback_error,
            "succeeded": self.succeeded,
        }
