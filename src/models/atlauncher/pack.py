from __future__ import annotations

from dataclasses import dataclass, field

from src.models.atlauncher.cache import ATLauncherCacheInfo
from src.models.atlauncher.version import ATLauncherVersionSummary


@dataclass(frozen=True, slots=True)
class ATLauncherPack:
    pack_id: str
    safe_name: str
    name: str
    synopsis: str = ""
    description: str = ""
    authors: tuple[str, ...] = ("ATLauncher",)
    icon_url: str = ""
    gallery_urls: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    position: int = 0
    updated_at: str = ""
    created_at: str = ""
    website_url: str = ""
    support_url: str = ""
    pack_type: str = ""
    versions: tuple[ATLauncherVersionSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class ATLauncherSearchResult:
    projects: tuple[ATLauncherPack, ...]
    total_count: int
    index: int
    page_size: int
    has_more: bool = False
    cache_info: ATLauncherCacheInfo = field(default_factory=ATLauncherCacheInfo)
