from __future__ import annotations

from pathlib import Path

from src.models.instance.instance import Instance
from src.models.modrinth.manual_download import ModrinthManualDownload


class ModrinthManagedFilesRequired(RuntimeError):
    def __init__(self, instance: Instance, requirements: tuple[ModrinthManualDownload, ...], message: str) -> None:
        super().__init__(message)
        self.instance_name = instance.name
        self.instance_dir = Path(instance.instance_dir)
        self.requirements = requirements
        self.launch_lock_token = ""


class ModrinthModpackManualDownloadRequired(RuntimeError):
    def __init__(self, requirement: ModrinthManualDownload, project_id: str, version_id: str, instance_name: str, install_optional_files: bool, allowed_version_types: tuple[str, ...], expected_loader: str = "", settings_override: dict | None = None) -> None:
        super().__init__(requirement.reason)
        self.requirement = requirement
        self.project_id = str(project_id)
        self.version_id = str(version_id)
        self.instance_name = str(instance_name)
        self.install_optional_files = bool(install_optional_files)
        self.allowed_version_types = tuple(allowed_version_types)
        self.expected_loader = str(expected_loader).strip().casefold()
        self.settings_override = dict(settings_override) if isinstance(settings_override, dict) else None
