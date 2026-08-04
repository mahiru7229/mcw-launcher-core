from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LanHostingComponent:
    role: str
    project_slug: str
    title: str


@dataclass(frozen=True, slots=True)
class LanHostingPlan:
    auth_mode: str
    connection_provider: str
    components: tuple[LanHostingComponent, ...]


@dataclass(frozen=True, slots=True)
class LanHostingPrepareResult:
    instance_name: str
    auth_mode: str
    connection_provider: str
    installed_projects: tuple[str, ...]
    reused_projects: tuple[str, ...]
    disabled_projects: tuple[str, ...]
    installed_files: tuple[str, ...]
    warnings: tuple[str, ...]
