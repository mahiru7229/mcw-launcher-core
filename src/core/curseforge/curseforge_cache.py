from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import time
from typing import Any
import hashlib
import json
import os

from src.config import CURSEFORGE_CACHE_MAX_BYTES, CURSEFORGE_MANUAL_REFRESH_COOLDOWN_SECONDS
from src.core.fs.paths import Paths
from src.models.curseforge.cache import CurseForgeCacheInfo


@dataclass(frozen=True, slots=True)
class CacheLookup:
    payload: Any
    cache_info: CurseForgeCacheInfo


class CurseForgeCache:
    SCHEMA_VERSION = 1
    MAX_SIZE_BYTES = CURSEFORGE_CACHE_MAX_BYTES
    TARGET_SIZE_BYTES = int(CURSEFORGE_CACHE_MAX_BYTES * 0.8)
    MANUAL_REFRESH_COOLDOWN_SECONDS = CURSEFORGE_MANUAL_REFRESH_COOLDOWN_SECONDS
    FAILURE_BACKOFF_SECONDS = (10, 30, 60, 120, 300)

    _lock = RLock()

    @staticmethod
    def root() -> Path:
        directory = Paths.curseforge_root() / "api-v2"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def entries_root() -> Path:
        directory = CurseForgeCache.root() / "entries"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def index_path() -> Path:
        return CurseForgeCache.root() / "index.json"

    @staticmethod
    def make_key(namespace: str, path: str, params: dict[str, object] | None = None, body: object | None = None) -> str:
        normalized = json.dumps(
            {
                "namespace": str(namespace).strip().casefold(),
                "path": str(path).strip(),
                "params": {str(key): value for key, value in sorted((params or {}).items())},
                "body": body,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def get(cache_key: str, ttl_seconds: int, allow_stale: bool = False) -> CacheLookup | None:
        with CurseForgeCache._lock:
            index = CurseForgeCache._load_index()
            metadata = index.get("entries", {}).get(cache_key)
            if not isinstance(metadata, dict):
                return None
            path = CurseForgeCache.entries_root() / f"{cache_key}.json"
            entry = CurseForgeCache._read_json(path)
            if not isinstance(entry, dict) or entry.get("schemaVersion") != CurseForgeCache.SCHEMA_VERSION or "payload" not in entry:
                CurseForgeCache._remove_entry(index, cache_key, path)
                CurseForgeCache._write_index(index)
                return None

            now = time()
            refreshed_at = float(entry.get("refreshedAt", 0) or 0)
            age = max(0, int(now - refreshed_at)) if refreshed_at > 0 else 2**31 - 1
            stale = ttl_seconds > 0 and age > max(0, int(ttl_seconds))
            if stale and not allow_stale:
                return None

            metadata["lastAccessedAt"] = now
            metadata["size"] = CurseForgeCache._safe_file_size(path)
            index["entries"][cache_key] = metadata
            CurseForgeCache._recalculate_size(index)
            CurseForgeCache._write_index(index)
            return CacheLookup(
                payload=entry.get("payload"),
                cache_info=CurseForgeCache._cache_info(
                    index,
                    refreshed_at=refreshed_at,
                    from_cache=True,
                    stale=stale,
                    age_seconds=age,
                ),
            )

    @staticmethod
    def put(cache_key: str, namespace: str, payload: object, ttl_seconds: int) -> CacheLookup:
        now = time()
        path = CurseForgeCache.entries_root() / f"{cache_key}.json"
        with CurseForgeCache._lock:
            index = CurseForgeCache._load_index()
            existing = index.get("entries", {}).get(cache_key)
            created_at = float(existing.get("createdAt", now) or now) if isinstance(existing, dict) else now
            entry = {
                "schemaVersion": CurseForgeCache.SCHEMA_VERSION,
                "namespace": str(namespace).strip().casefold(),
                "createdAt": created_at,
                "refreshedAt": now,
                "expiresAt": now + max(0, int(ttl_seconds)),
                "payload": payload,
            }
            CurseForgeCache._write_json_atomic(path, entry)
            index.setdefault("entries", {})[cache_key] = {
                "namespace": str(namespace).strip().casefold(),
                "path": path.name,
                "createdAt": created_at,
                "refreshedAt": now,
                "expiresAt": entry["expiresAt"],
                "lastAccessedAt": now,
                "size": CurseForgeCache._safe_file_size(path),
            }
            provider = index.setdefault("provider", CurseForgeCache._empty_provider())
            provider["lastSuccessfulRefreshAt"] = now
            provider["lastRefreshError"] = ""
            provider["consecutiveFailures"] = 0
            provider["nextManualRefreshAt"] = max(
                float(provider.get("nextManualRefreshAt", 0) or 0),
                now + CurseForgeCache.MANUAL_REFRESH_COOLDOWN_SECONDS,
            )
            CurseForgeCache._recalculate_size(index)
            CurseForgeCache._evict(index)
            CurseForgeCache._write_index(index)
            return CacheLookup(
                payload=payload,
                cache_info=CurseForgeCache._cache_info(
                    index,
                    refreshed_at=now,
                    from_cache=False,
                    stale=False,
                    age_seconds=0,
                ),
            )

    @staticmethod
    def record_attempt(manual: bool = False) -> None:
        with CurseForgeCache._lock:
            index = CurseForgeCache._load_index()
            provider = index.setdefault("provider", CurseForgeCache._empty_provider())
            now = time()
            provider["lastRefreshAttemptAt"] = now
            if manual:
                provider["nextManualRefreshAt"] = max(
                    float(provider.get("nextManualRefreshAt", 0) or 0),
                    now + CurseForgeCache.MANUAL_REFRESH_COOLDOWN_SECONDS,
                )
            CurseForgeCache._write_index(index)

    @staticmethod
    def record_failure(message: str, retry_after_seconds: int | None = None) -> None:
        with CurseForgeCache._lock:
            index = CurseForgeCache._load_index()
            provider = index.setdefault("provider", CurseForgeCache._empty_provider())
            failures = max(0, int(provider.get("consecutiveFailures", 0) or 0)) + 1
            provider["consecutiveFailures"] = failures
            provider["lastRefreshError"] = str(message).strip()[:500]
            delay = CurseForgeCache.FAILURE_BACKOFF_SECONDS[min(failures - 1, len(CurseForgeCache.FAILURE_BACKOFF_SECONDS) - 1)]
            if retry_after_seconds is not None:
                delay = max(delay, max(0, int(retry_after_seconds)))
            provider["nextManualRefreshAt"] = max(float(provider.get("nextManualRefreshAt", 0) or 0), time() + delay)
            CurseForgeCache._write_index(index)

    @staticmethod
    def manual_refresh_remaining_seconds() -> int:
        with CurseForgeCache._lock:
            provider = CurseForgeCache._load_index().get("provider", {})
            return max(0, int(float(provider.get("nextManualRefreshAt", 0) or 0) - time() + 0.999))

    @staticmethod
    def assert_manual_refresh_allowed() -> None:
        remaining = CurseForgeCache.manual_refresh_remaining_seconds()
        if remaining > 0:
            raise RuntimeError(f"CurseForge refresh is on cooldown. Try again in {remaining} second(s).")

    @staticmethod
    def status() -> CurseForgeCacheInfo:
        with CurseForgeCache._lock:
            index = CurseForgeCache._load_index()
            provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
            refreshed = float(provider.get("lastSuccessfulRefreshAt", 0) or 0)
            age = max(0, int(time() - refreshed)) if refreshed > 0 else 0
            return CurseForgeCache._cache_info(index, refreshed_at=refreshed, from_cache=False, stale=False, age_seconds=age)

    @staticmethod
    def clear() -> None:
        with CurseForgeCache._lock:
            root = CurseForgeCache.entries_root()
            for path in root.glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
            index = CurseForgeCache._empty_index()
            CurseForgeCache._write_index(index)

    @staticmethod
    def _cache_info(index: dict, refreshed_at: float, from_cache: bool, stale: bool, age_seconds: int) -> CurseForgeCacheInfo:
        provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
        return CurseForgeCacheInfo(
            refreshed_at=CurseForgeCache._iso(refreshed_at),
            from_cache=bool(from_cache),
            stale=bool(stale),
            age_seconds=max(0, int(age_seconds)),
            next_manual_refresh_at=CurseForgeCache._iso(float(provider.get("nextManualRefreshAt", 0) or 0)),
            last_error=str(provider.get("lastRefreshError") or ""),
            cache_size_bytes=max(0, int(index.get("totalSize", 0) or 0)),
            cache_limit_bytes=CurseForgeCache.MAX_SIZE_BYTES,
        )

    @staticmethod
    def _empty_provider() -> dict[str, object]:
        return {
            "lastRefreshAttemptAt": 0.0,
            "lastSuccessfulRefreshAt": 0.0,
            "lastRefreshError": "",
            "nextManualRefreshAt": 0.0,
            "consecutiveFailures": 0,
        }

    @staticmethod
    def _empty_index() -> dict[str, object]:
        return {
            "schemaVersion": CurseForgeCache.SCHEMA_VERSION,
            "maximumSize": CurseForgeCache.MAX_SIZE_BYTES,
            "targetSize": CurseForgeCache.TARGET_SIZE_BYTES,
            "totalSize": 0,
            "lastCleanupAt": 0.0,
            "provider": CurseForgeCache._empty_provider(),
            "entries": {},
        }

    @staticmethod
    def _load_index() -> dict:
        data = CurseForgeCache._read_json(CurseForgeCache.index_path())
        if not isinstance(data, dict) or data.get("schemaVersion") != CurseForgeCache.SCHEMA_VERSION:
            return CurseForgeCache._empty_index()
        data.setdefault("entries", {})
        data.setdefault("provider", CurseForgeCache._empty_provider())
        data["maximumSize"] = CurseForgeCache.MAX_SIZE_BYTES
        data["targetSize"] = CurseForgeCache.TARGET_SIZE_BYTES
        return data

    @staticmethod
    def _write_index(index: dict) -> None:
        CurseForgeCache._write_json_atomic(CurseForgeCache.index_path(), index)

    @staticmethod
    def _evict(index: dict) -> None:
        CurseForgeCache._recalculate_size(index)
        if int(index.get("totalSize", 0) or 0) <= CurseForgeCache.MAX_SIZE_BYTES:
            return
        entries = index.get("entries", {}) if isinstance(index.get("entries"), dict) else {}
        ordered = sorted(
            entries.items(),
            key=lambda item: (
                float(item[1].get("lastAccessedAt", 0) or 0) if isinstance(item[1], dict) else 0,
                float(item[1].get("refreshedAt", 0) or 0) if isinstance(item[1], dict) else 0,
            ),
        )
        for cache_key, _metadata in ordered:
            path = CurseForgeCache.entries_root() / f"{cache_key}.json"
            CurseForgeCache._remove_entry(index, cache_key, path)
            CurseForgeCache._recalculate_size(index)
            if int(index.get("totalSize", 0) or 0) <= CurseForgeCache.TARGET_SIZE_BYTES:
                break
        index["lastCleanupAt"] = time()

    @staticmethod
    def _remove_entry(index: dict, cache_key: str, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass
        entries = index.get("entries")
        if isinstance(entries, dict):
            entries.pop(cache_key, None)

    @staticmethod
    def _recalculate_size(index: dict) -> None:
        entries = index.get("entries", {}) if isinstance(index.get("entries"), dict) else {}
        total = 0
        missing: list[str] = []
        for cache_key, metadata in entries.items():
            path = CurseForgeCache.entries_root() / f"{cache_key}.json"
            size = CurseForgeCache._safe_file_size(path)
            if size <= 0 and not path.exists():
                missing.append(cache_key)
                continue
            if isinstance(metadata, dict):
                metadata["size"] = size
            total += size
        for cache_key in missing:
            entries.pop(cache_key, None)
        index["totalSize"] = total

    @staticmethod
    def _read_json(path: Path) -> object | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json_atomic(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(data, output, ensure_ascii=False, separators=(",", ":"))
            output.write("\n")
            output.flush()
            try:
                os.fsync(output.fileno())
            except OSError:
                pass
        temporary.replace(path)

    @staticmethod
    def _safe_file_size(path: Path) -> int:
        try:
            return max(0, int(path.stat().st_size))
        except OSError:
            return 0

    @staticmethod
    def _iso(timestamp: float) -> str:
        if timestamp <= 0:
            return ""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
