from __future__ import annotations

from dataclasses import dataclass, field

from src.models.curseforge.cache import CurseForgeCacheInfo


@dataclass(frozen=True, slots=True)
class CurseForgeProject:
    project_id: int
    name: str
    slug: str
    summary: str
    download_count: int
    authors: tuple[str, ...]
    logo_url: str
    class_id: int
    date_modified: str
    project_url: str = ""
    game_versions: tuple[str, ...] = ()
    loaders: tuple[str, ...] = ()
    description: str = ""
    source_url: str = ""
    issues_url: str = ""
    wiki_url: str = ""
    categories: tuple[str, ...] = ()
    screenshot_urls: tuple[str, ...] = ()
    date_created: str = ""
    date_released: str = ""
    status: str = ""
    is_featured: bool = False


@dataclass(frozen=True, slots=True)
class CurseForgeSearchResult:
    projects: tuple[CurseForgeProject, ...]
    total_count: int
    index: int
    page_size: int
    cache_info: CurseForgeCacheInfo = field(default_factory=CurseForgeCacheInfo)
