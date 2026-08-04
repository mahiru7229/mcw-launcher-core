from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModInfo:
    path: Path
    file_name: str
    enabled: bool
    mod_id: str
    name: str
    version: str
    loader: str = "unknown"
    metadata_format: str = "unknown"
    description: str = ""
    environment: str = "*"
    authors: tuple[str, ...] = ()
    licenses: tuple[str, ...] = ()
    dependencies: dict[str, object] = field(default_factory=dict)
    recommends: dict[str, object] = field(default_factory=dict)
    suggests: dict[str, object] = field(default_factory=dict)
    conflicts: dict[str, object] = field(default_factory=dict)
    breaks: dict[str, object] = field(default_factory=dict)
    status: str = "Ready"
    error: str = ""
    source: str = "local"
    source_project_id: str = ""
    source_version_id: str = ""
    source_file_id: str = ""
    managed_by_modpack: bool = False
    source_pack_provider: str = ""
