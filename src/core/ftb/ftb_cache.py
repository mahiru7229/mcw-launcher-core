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

from src.core.fs.paths import Paths
from src.models.ftb.cache import FTBCacheInfo


@dataclass(frozen=True, slots=True)
class FTBApiCacheLookup:
    payload: Any
    cache_info: FTBCacheInfo


class FTBApiCache:
    SCHEMA_VERSION = 1
    MAX_SIZE_BYTES = 10 * 1024 * 1024
    TARGET_SIZE_BYTES = 8 * 1024 * 1024
    _lock = RLock()

    @staticmethod
    def root() -> Path:
        directory = Paths.ftb_api_cache_root()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def entries_root() -> Path:
        directory = FTBApiCache.root() / "entries"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def index_path() -> Path:
        return FTBApiCache.root() / "index.json"

    @staticmethod
    def make_key(namespace: str, path: str, params: dict[str, object] | None = None) -> str:
        value = json.dumps(
            {"namespace": str(namespace).casefold(), "path": str(path), "params": dict(sorted((params or {}).items()))},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def get(cache_key: str, ttl_seconds: int, allow_stale: bool = False) -> FTBApiCacheLookup | None:
        with FTBApiCache._lock:
            index = FTBApiCache._load_index()
            metadata = index.get("entries", {}).get(cache_key)
            if not isinstance(metadata, dict):
                return None
            path = FTBApiCache.entries_root() / f"{cache_key}.json"
            entry = FTBApiCache._read_json(path)
            if not isinstance(entry, dict) or entry.get("schemaVersion") != FTBApiCache.SCHEMA_VERSION or "payload" not in entry:
                FTBApiCache._remove_entry(index, cache_key, path)
                FTBApiCache._write_index(index)
                return None
            refreshed_at = float(entry.get("refreshedAt", 0) or 0)
            age = max(0, int(time() - refreshed_at)) if refreshed_at > 0 else 2**31 - 1
            stale = ttl_seconds > 0 and age > max(0, int(ttl_seconds))
            if stale and not allow_stale:
                return None
            metadata["lastAccessedAt"] = time()
            metadata["size"] = FTBApiCache._safe_size(path)
            FTBApiCache._recalculate(index)
            FTBApiCache._write_index(index)
            return FTBApiCacheLookup(
                payload=entry.get("payload"),
                cache_info=FTBApiCache._info(index, refreshed_at, True, stale, age),
            )

    @staticmethod
    def put(cache_key: str, namespace: str, payload: object, ttl_seconds: int) -> FTBApiCacheLookup:
        now = time()
        path = FTBApiCache.entries_root() / f"{cache_key}.json"
        with FTBApiCache._lock:
            index = FTBApiCache._load_index()
            entry = {
                "schemaVersion": FTBApiCache.SCHEMA_VERSION,
                "namespace": str(namespace).strip().casefold(),
                "refreshedAt": now,
                "expiresAt": now + max(0, int(ttl_seconds)),
                "payload": payload,
            }
            FTBApiCache._write_json_atomic(path, entry)
            index.setdefault("entries", {})[cache_key] = {
                "namespace": entry["namespace"],
                "refreshedAt": now,
                "lastAccessedAt": now,
                "size": FTBApiCache._safe_size(path),
            }
            provider = index.setdefault("provider", {})
            provider["lastSuccessfulRefreshAt"] = now
            provider["lastRefreshError"] = ""
            FTBApiCache._recalculate(index)
            FTBApiCache._evict(index)
            FTBApiCache._write_index(index)
            return FTBApiCacheLookup(payload=payload, cache_info=FTBApiCache._info(index, now, False, False, 0))

    @staticmethod
    def record_failure(message: str) -> None:
        with FTBApiCache._lock:
            index = FTBApiCache._load_index()
            index.setdefault("provider", {})["lastRefreshError"] = str(message).strip()[:500]
            FTBApiCache._write_index(index)

    @staticmethod
    def status() -> FTBCacheInfo:
        with FTBApiCache._lock:
            index = FTBApiCache._load_index()
            provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
            refreshed = float(provider.get("lastSuccessfulRefreshAt", 0) or 0)
            age = max(0, int(time() - refreshed)) if refreshed > 0 else 0
            return FTBApiCache._info(index, refreshed, False, False, age)

    @staticmethod
    def clear() -> None:
        with FTBApiCache._lock:
            for path in FTBApiCache.entries_root().glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
            FTBApiCache._write_index(FTBApiCache._empty_index())

    @staticmethod
    def _empty_index() -> dict[str, object]:
        return {
            "schemaVersion": FTBApiCache.SCHEMA_VERSION,
            "totalSize": 0,
            "provider": {"lastSuccessfulRefreshAt": 0.0, "lastRefreshError": ""},
            "entries": {},
        }

    @staticmethod
    def _load_index() -> dict:
        data = FTBApiCache._read_json(FTBApiCache.index_path())
        if not isinstance(data, dict) or data.get("schemaVersion") != FTBApiCache.SCHEMA_VERSION:
            return FTBApiCache._empty_index()
        data.setdefault("entries", {})
        data.setdefault("provider", {})
        return data

    @staticmethod
    def _write_index(index: dict) -> None:
        FTBApiCache._write_json_atomic(FTBApiCache.index_path(), index)

    @staticmethod
    def _evict(index: dict) -> None:
        FTBApiCache._recalculate(index)
        if int(index.get("totalSize", 0) or 0) <= FTBApiCache.MAX_SIZE_BYTES:
            return
        entries = index.get("entries", {}) if isinstance(index.get("entries"), dict) else {}
        ordered = sorted(entries.items(), key=lambda item: float(item[1].get("lastAccessedAt", 0) or 0) if isinstance(item[1], dict) else 0)
        for cache_key, _ in ordered:
            FTBApiCache._remove_entry(index, cache_key, FTBApiCache.entries_root() / f"{cache_key}.json")
            FTBApiCache._recalculate(index)
            if int(index.get("totalSize", 0) or 0) <= FTBApiCache.TARGET_SIZE_BYTES:
                break

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
    def _recalculate(index: dict) -> None:
        entries = index.get("entries", {}) if isinstance(index.get("entries"), dict) else {}
        total = 0
        missing: list[str] = []
        for key, metadata in entries.items():
            path = FTBApiCache.entries_root() / f"{key}.json"
            if not path.exists():
                missing.append(key)
                continue
            size = FTBApiCache._safe_size(path)
            if isinstance(metadata, dict):
                metadata["size"] = size
            total += size
        for key in missing:
            entries.pop(key, None)
        index["totalSize"] = total

    @staticmethod
    def _info(index: dict, refreshed_at: float, from_cache: bool, stale: bool, age: int) -> FTBCacheInfo:
        provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
        return FTBCacheInfo(
            refreshed_at=FTBApiCache._iso(refreshed_at),
            from_cache=bool(from_cache),
            stale=bool(stale),
            age_seconds=max(0, int(age)),
            last_error=str(provider.get("lastRefreshError") or ""),
            cache_size_bytes=max(0, int(index.get("totalSize", 0) or 0)),
            cache_limit_bytes=FTBApiCache.MAX_SIZE_BYTES,
        )

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
    def _safe_size(path: Path) -> int:
        try:
            return max(0, int(path.stat().st_size))
        except OSError:
            return 0

    @staticmethod
    def _iso(timestamp: float) -> str:
        if timestamp <= 0:
            return ""
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


# Backward-compatible alias for extensions/tests built before v1.3.
FTBCache = FTBApiCache
