from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurseForgeCacheInfo:
    refreshed_at: str = ""
    from_cache: bool = False
    stale: bool = False
    age_seconds: int = 0
    next_manual_refresh_at: str = ""
    last_error: str = ""
    cache_size_bytes: int = 0
    cache_limit_bytes: int = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CurseForgeFileListResult:
    files: tuple[object, ...]
    cache_info: CurseForgeCacheInfo
