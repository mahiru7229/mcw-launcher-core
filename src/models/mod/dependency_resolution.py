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
        display_messages = self._display_messages(self.issues)
        details = "\n".join(f"- {message}" for message in display_messages)
        requirement_count = len(self.issues)
        summary = f"{len(display_messages)} blocking dependency group(s) remain."
        if requirement_count != len(display_messages):
            summary += f" ({requirement_count} mod requirement(s) were grouped.)"
        super().__init__(
            f"Required mod dependencies are unresolved for '{self.instance_name}'.\n"
            f"{summary}\n"
            f"{details}"
        )

    @staticmethod
    def _display_messages(issues: tuple[ModIssue, ...]) -> tuple[str, ...]:
        dependency_groups: dict[tuple[str, str], list[ModIssue]] = {}
        standalone: list[str] = []
        for issue in issues:
            if issue.code in {"dependency-missing", "dependency-disabled", "dependency-version"} and len(issue.mod_ids) >= 2:
                dependency_id = str(issue.mod_ids[1]).strip().casefold()
                dependency_groups.setdefault((issue.code, dependency_id), []).append(issue)
            else:
                standalone.append(issue.message)

        grouped: list[str] = []
        for (_code, dependency_id), entries in dependency_groups.items():
            if len(entries) == 1:
                grouped.append(entries[0].message)
                continue
            parents = tuple(
                dict.fromkeys(str(entry.mod_ids[0]).strip() for entry in entries if str(entry.mod_ids[0]).strip())
            )
            preview = ", ".join(parents[:6])
            if len(parents) > 6:
                preview += f", and {len(parents) - 6} more"
            grouped.append(
                f"Dependency '{dependency_id}' has {len(entries)} blocking requirement(s)"
                + (f" from: {preview}." if preview else ".")
            )
        return tuple(grouped + standalone)
