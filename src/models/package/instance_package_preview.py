from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.models.package.package_metadata import PackageMetadata


@dataclass(frozen=True, slots=True)
class InstancePackagePreview:
    package_path: Path
    name: str
    version_id: str
    mod_loader: tuple[str, str]
    icon: str
    settings: dict[str, Any]
    has_package_settings: bool
    package_metadata: PackageMetadata
