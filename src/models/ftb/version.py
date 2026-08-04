from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FTBTarget:
    target_id: int
    target_type: str
    name: str
    version: str
    updated: int = 0


@dataclass(frozen=True, slots=True)
class FTBVersionSummary:
    version_id: int
    name: str
    release_type: str
    updated: int
    private: bool
    targets: tuple[FTBTarget, ...] = ()

    @property
    def minecraft_version(self) -> str:
        return next((target.version for target in self.targets if target.target_type == "game" and target.name.casefold() == "minecraft"), "")

    @property
    def loader(self) -> str:
        return next((target.name.casefold() for target in self.targets if target.target_type == "modloader"), "")

    @property
    def loader_version(self) -> str:
        return next((target.version for target in self.targets if target.target_type == "modloader"), "")


@dataclass(frozen=True, slots=True)
class FTBFile:
    file_id: int
    name: str
    path: str
    version: str
    file_type: str
    urls: tuple[str, ...]
    sha1: str
    size: int
    client_only: bool = False
    server_only: bool = False
    optional: bool = False

    @property
    def file_name(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class FTBVersion:
    project_id: int
    version_id: int
    name: str
    release_type: str
    files: tuple[FTBFile, ...]
    targets: tuple[FTBTarget, ...]
    status: str = ""
    notification: str = ""
    minimum_memory_mb: int = 0
    recommended_memory_mb: int = 0

    @property
    def minecraft_version(self) -> str:
        return next((target.version for target in self.targets if target.target_type == "game" and target.name.casefold() == "minecraft"), "")

    @property
    def loader(self) -> str:
        return next((target.name.casefold() for target in self.targets if target.target_type == "modloader"), "")

    @property
    def loader_version(self) -> str:
        return next((target.version for target in self.targets if target.target_type == "modloader"), "")

    @property
    def java_version(self) -> str:
        return next((target.version for target in self.targets if target.target_type == "runtime" and target.name.casefold() == "java"), "")

    @property
    def downloadable_size(self) -> int:
        return sum(max(0, file.size) for file in self.files if not file.server_only)
