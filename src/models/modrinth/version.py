from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModrinthFile:
    url: str
    filename: str
    sha1: str
    sha512: str
    size: int
    primary: bool = False


@dataclass(frozen=True, slots=True)
class ModrinthDependency:
    dependency_type: str
    project_id: str = ""
    version_id: str = ""
    file_name: str = ""


@dataclass(frozen=True, slots=True)
class ModrinthVersion:
    version_id: str
    project_id: str
    name: str
    version_number: str
    version_type: str
    game_versions: tuple[str, ...]
    loaders: tuple[str, ...]
    files: tuple[ModrinthFile, ...]
    dependencies: tuple[ModrinthDependency, ...] = ()
    featured: bool = False
    date_published: str = ""

    def primary_file(self, suffix: str | None = None) -> ModrinthFile:
        candidates = self.files
        if suffix:
            normalized = suffix.casefold()
            candidates = tuple(file for file in candidates if file.filename.casefold().endswith(normalized))
        if not candidates:
            label = suffix or "downloadable"
            raise RuntimeError(f"Modrinth version '{self.version_number}' has no {label} file.")
        return next((file for file in candidates if file.primary), candidates[0])
