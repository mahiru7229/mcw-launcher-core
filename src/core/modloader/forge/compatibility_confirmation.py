from __future__ import annotations

from src.models.modloader.forge_preflight_report import ForgePreflightReport


class CompatibilityConfirmationRequired(RuntimeError):
    """Raised when bypassable compatibility errors require user consent."""

    def __init__(self, instance_name: str, report: ForgePreflightReport) -> None:
        self.instance_name = str(instance_name)
        self.report = report
        self.issues = tuple(report.errors)
        details = "\n".join(f"- {issue.message}" for issue in self.issues)
        super().__init__(
            "Compatibility confirmation is required before launch.\n"
            f"{len(self.issues)} bypassable issue(s) were found for '{self.instance_name}'.\n"
            f"{details}"
        )
