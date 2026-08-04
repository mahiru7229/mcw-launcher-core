from __future__ import annotations

from pathlib import Path

from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.instance.instance import Instance


class CurseForgeManagedFilesRequired(RuntimeError):
    """Raised when managed CurseForge files require user-assisted recovery."""

    def __init__(self, instance: Instance, requirements: tuple[CurseForgeManualDownload, ...], message: str) -> None:
        super().__init__(message)
        self.instance_name = instance.name
        self.instance_dir = Path(instance.instance_dir)
        self.requirements = requirements


class CurseForgeModpackManualDownloadRequired(RuntimeError):
    """Raised when a CurseForge modpack archive must be downloaded manually."""

    def __init__(self, requirement: CurseForgeManualDownload, project_id: int, file_id: int, instance_name: str, install_optional_files: bool, allowed_release_types: tuple[str, ...], expected_loader: str = "", settings_override: dict | None = None) -> None:
        super().__init__(requirement.reason)
        self.requirement = requirement
        self.project_id = int(project_id)
        self.file_id = int(file_id)
        self.instance_name = str(instance_name)
        self.install_optional_files = bool(install_optional_files)
        self.allowed_release_types = tuple(allowed_release_types)
        self.expected_loader = str(expected_loader).strip().casefold()
        self.settings_override = dict(settings_override) if isinstance(settings_override, dict) else None
