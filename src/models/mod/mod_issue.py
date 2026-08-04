from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModIssue:
    severity: str
    code: str
    message: str
    mod_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModHealthReport:
    issues: tuple[ModIssue, ...]
    enabled_mods: int
    disabled_mods: int

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def is_healthy(self) -> bool:
        return self.error_count == 0
