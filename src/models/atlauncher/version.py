from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ATLauncherVersionSummary:
    version_id: str
    version: str
    minecraft_version: str = ""
    changelog: str = ""
    recommended: bool = False
    development: bool = False
    created_at: str = ""
    updated_at: str = ""
    published_at: str = ""

    @property
    def release_type(self) -> str:
        if self.development:
            return "alpha"
        return "release" if self.recommended else "beta"


@dataclass(frozen=True, slots=True)
class ATLauncherFile:
    file_id: str
    name: str
    path: str
    urls: tuple[str, ...]
    sha1: str = ""
    md5: str = ""
    size: int = 0
    download_type: str = "direct"
    optional: bool = False
    selected: bool = False
    recommended: bool = False
    client_only: bool = False
    server_only: bool = False
    library: bool = False
    dependencies: tuple[str, ...] = ()
    extract_to: str = ""
    extract_folder: str = ""
    decomp_type: str = ""
    decomp_file: str = ""
    force: bool = False

    @property
    def file_name(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class ATLauncherConfigBundle:
    url: str
    sha1: str
    size: int


@dataclass(frozen=True, slots=True)
class ATLauncherVersion:
    pack_id: str
    safe_name: str
    version_id: str
    version: str
    minecraft_version: str
    changelog: str
    recommended: bool
    development: bool
    loader: str
    loader_version: str
    files: tuple[ATLauncherFile, ...]
    config_bundle: ATLauncherConfigBundle | None = None
    minimum_memory_mb: int = 0
    recommended_memory_mb: int = 0
    java_version: str = ""
    warnings: tuple[str, ...] = ()
    unsupported_actions: tuple[str, ...] = ()
    published_at: str = ""
    raw_manifest: dict | None = None

    @property
    def release_type(self) -> str:
        if self.development:
            return "alpha"
        return "release" if self.recommended else "beta"

    @property
    def downloadable_size(self) -> int:
        total = sum(max(0, file.size) for file in self.files if not file.server_only)
        if self.config_bundle is not None:
            total += max(0, self.config_bundle.size)
        return total
