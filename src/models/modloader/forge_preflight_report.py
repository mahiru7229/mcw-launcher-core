from __future__ import annotations

from dataclasses import dataclass

from src.models.mod.mod_issue import ModIssue


@dataclass(frozen=True, slots=True)
class ForgePreflightReport:
    issues: tuple[ModIssue, ...]
    loader: str = "forge"

    @property
    def errors(self) -> tuple[ModIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ModIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def can_launch(self) -> bool:
        return not self.errors

    def format_summary(self) -> str:
        return f"{self.error_count} error(s), {self.warning_count} warning(s)"
