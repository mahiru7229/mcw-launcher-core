from __future__ import annotations

from dataclasses import dataclass

from src.models.mod.mod_issue import ModIssue


@dataclass(frozen=True, slots=True)
class DependencyResolutionResult:
    added_files: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.added_files)


class RequiredModDependenciesMissing(RuntimeError):
    """Raised when required mod dependencies remain unresolved before launch."""

    def __init__(self, instance_name: str, issues: tuple[ModIssue, ...]) -> None:
        self.instance_name = str(instance_name)
        self.issues = tuple(issues)
        details = "\n".join(f"- {issue.message}" for issue in self.issues)
        super().__init__(
            f"Required mod dependencies are unresolved for '{self.instance_name}'.\n"
            f"{len(self.issues)} blocking dependency issue(s) remain.\n"
            f"{details}"
        )
