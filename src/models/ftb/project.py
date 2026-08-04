from __future__ import annotations

from dataclasses import dataclass, field

from src.models.ftb.cache import FTBCacheInfo
from src.models.ftb.version import FTBVersionSummary


@dataclass(frozen=True, slots=True)
class FTBProject:
    project_id: int
    name: str
    synopsis: str = ""
    description: str = ""
    authors: tuple[str, ...] = ()
    icon_url: str = ""
    gallery_urls: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    plays: int = 0
    updated_at: str = ""
    created_at: str = ""
    website_url: str = ""
    versions: tuple[FTBVersionSummary, ...] = ()
    private: bool = False
    status: str = ""


@dataclass(frozen=True, slots=True)
class FTBSearchResult:
    projects: tuple[FTBProject, ...]
    total_count: int
    index: int
    page_size: int
    cache_info: FTBCacheInfo = field(default_factory=FTBCacheInfo)
