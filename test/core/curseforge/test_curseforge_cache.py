from pathlib import Path

import src.core.curseforge.curseforge_cache as cache_module
from src.core.curseforge.curseforge_cache import CurseForgeCache


def configure_cache(monkeypatch, tmp_path: Path, now: list[float]) -> None:
    monkeypatch.setattr(CurseForgeCache, "root", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(cache_module, "time", lambda: now[0])


def test_cache_tracks_refresh_time_and_stale_state(monkeypatch, tmp_path: Path) -> None:
    now = [1_000.0]
    configure_cache(monkeypatch, tmp_path, now)
    key = CurseForgeCache.make_key("search", "/search", {"query": "sodium"})

    written = CurseForgeCache.put(key, "search", {"data": [1]}, ttl_seconds=60)

    assert written.cache_info.from_cache is False
    assert written.cache_info.refreshed_at == "1970-01-01T00:16:40Z"
    assert written.cache_info.cache_size_bytes > 0

    now[0] = 1_030.0
    fresh = CurseForgeCache.get(key, ttl_seconds=60)
    assert fresh is not None
    assert fresh.payload == {"data": [1]}
    assert fresh.cache_info.from_cache is True
    assert fresh.cache_info.stale is False
    assert fresh.cache_info.age_seconds == 30

    now[0] = 1_061.0
    assert CurseForgeCache.get(key, ttl_seconds=60) is None
    stale = CurseForgeCache.get(key, ttl_seconds=60, allow_stale=True)
    assert stale is not None
    assert stale.cache_info.stale is True
    assert stale.cache_info.age_seconds == 61


def test_manual_refresh_cooldown_and_failure_backoff(monkeypatch, tmp_path: Path) -> None:
    now = [2_000.0]
    configure_cache(monkeypatch, tmp_path, now)

    CurseForgeCache.record_attempt(manual=True)
    assert CurseForgeCache.manual_refresh_remaining_seconds() == 60

    now[0] += 60
    assert CurseForgeCache.manual_refresh_remaining_seconds() == 0

    CurseForgeCache.record_failure("Gateway timeout")
    status = CurseForgeCache.status()
    assert status.last_error == "Gateway timeout"
    assert CurseForgeCache.manual_refresh_remaining_seconds() == 10

    now[0] += 10
    CurseForgeCache.record_failure("Gateway timeout again", retry_after_seconds=45)
    assert CurseForgeCache.manual_refresh_remaining_seconds() == 45


def test_cache_evicts_least_recently_used_entries(monkeypatch, tmp_path: Path) -> None:
    now = [3_000.0]
    configure_cache(monkeypatch, tmp_path, now)
    monkeypatch.setattr(CurseForgeCache, "MAX_SIZE_BYTES", 2_400)
    monkeypatch.setattr(CurseForgeCache, "TARGET_SIZE_BYTES", 1_200)

    keys = []
    for index in range(4):
        key = CurseForgeCache.make_key("project", "/mod", {"modId": index + 1})
        keys.append(key)
        CurseForgeCache.put(key, "project", {"value": str(index) * 700}, ttl_seconds=3600)
        now[0] += 1

    status = CurseForgeCache.status()
    assert status.cache_size_bytes <= CurseForgeCache.MAX_SIZE_BYTES
    assert CurseForgeCache.get(keys[0], ttl_seconds=3600) is None
    assert CurseForgeCache.get(keys[-1], ttl_seconds=3600) is not None


def test_clear_removes_entries_but_preserves_usable_cache(monkeypatch, tmp_path: Path) -> None:
    now = [4_000.0]
    configure_cache(monkeypatch, tmp_path, now)
    key = CurseForgeCache.make_key("file", "/file", {"fileId": 1})
    CurseForgeCache.put(key, "file", {"data": {"id": 1}}, ttl_seconds=3600)

    CurseForgeCache.clear()

    assert CurseForgeCache.get(key, ttl_seconds=3600) is None
    assert CurseForgeCache.status().cache_size_bytes == 0
    assert CurseForgeCache.index_path().is_file()
