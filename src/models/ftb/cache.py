from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FTBCacheInfo:
    refreshed_at: str = ""
    from_cache: bool = False
    stale: bool = False
    age_seconds: int = 0
    last_error: str = ""
    cache_size_bytes: int = 0
    cache_limit_bytes: int = 10 * 1024 * 1024
