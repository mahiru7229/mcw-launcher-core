from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurseForgeDependency:
    project_id: int
    relation_type: int

    @property
    def required(self) -> bool:
        return self.relation_type == 3


@dataclass(frozen=True, slots=True)
class CurseForgeFile:
    file_id: int
    project_id: int
    display_name: str
    file_name: str
    release_type: str
    file_date: str
    file_length: int
    download_url: str
    sha1: str
    game_versions: tuple[str, ...]
    dependencies: tuple[CurseForgeDependency, ...]
    is_available: bool = True
    loaders: tuple[str, ...] = ()

    @property
    def version_number(self) -> str:
        return self.display_name

    @property
    def size(self) -> int:
        return self.file_length

    @property
    def url(self) -> str:
        return self.download_url
