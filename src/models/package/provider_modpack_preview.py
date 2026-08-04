from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderModpackPreview:
    package_path: Path
    provider: str
    package_format: str
    name: str
    version_id: str
    version_label: str
    version_id_source: str
    version_id_is_provider_native: bool
    minecraft_version: str
    mod_loader: tuple[str, str]
    file_count: int
    summary: str = ""
    icon: str = "grass_block"
    settings: dict[str, Any] = field(default_factory=dict)
    has_package_settings: bool = False
    install_optional_files: bool = True
    provider_reference: dict[str, Any] = field(default_factory=dict)
    native_package_member: str = ""

    @property
    def version_id_for_instance(self) -> str:
        return self.minecraft_version
