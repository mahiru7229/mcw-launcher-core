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
from src.models.atlauncher.cache import ATLauncherCacheInfo


@dataclass(frozen=True, slots=True)
class ATLauncherCacheLookup:
    payload: Any
    cache_info: ATLauncherCacheInfo


class ATLauncherCache:
    SCHEMA_VERSION = 1
    MAX_SIZE_BYTES = 10 * 1024 * 1024
    TARGET_SIZE_BYTES = 8 * 1024 * 1024
    _lock = RLock()

    @staticmethod
    def root() -> Path:
        directory = Paths.atlauncher_root() / "api"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def entries_root() -> Path:
        directory = ATLauncherCache.root() / "entries"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def index_path() -> Path:
        return ATLauncherCache.root() / "index.json"

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
    def get(cache_key: str, ttl_seconds: int, allow_stale: bool = False) -> ATLauncherCacheLookup | None:
        with ATLauncherCache._lock:
            index = ATLauncherCache._load_index()
            metadata = index.get("entries", {}).get(cache_key)
            if not isinstance(metadata, dict):
                return None
            path = ATLauncherCache.entries_root() / f"{cache_key}.json"
            entry = ATLauncherCache._read_json(path)
            if not isinstance(entry, dict) or entry.get("schemaVersion") != ATLauncherCache.SCHEMA_VERSION or "payload" not in entry:
                ATLauncherCache._remove_entry(index, cache_key, path)
                ATLauncherCache._write_index(index)
                return None
            refreshed_at = float(entry.get("refreshedAt", 0) or 0)
            age = max(0, int(time() - refreshed_at)) if refreshed_at > 0 else 2**31 - 1
            stale = ttl_seconds > 0 and age > max(0, int(ttl_seconds))
            if stale and not allow_stale:
                return None
            metadata["lastAccessedAt"] = time()
            metadata["size"] = ATLauncherCache._safe_size(path)
            ATLauncherCache._recalculate(index)
            ATLauncherCache._write_index(index)
            return ATLauncherCacheLookup(
                payload=entry.get("payload"),
                cache_info=ATLauncherCache._info(index, refreshed_at, True, stale, age),
            )

    @staticmethod
    def put(cache_key: str, namespace: str, payload: object, ttl_seconds: int) -> ATLauncherCacheLookup:
        now = time()
        path = ATLauncherCache.entries_root() / f"{cache_key}.json"
        with ATLauncherCache._lock:
            index = ATLauncherCache._load_index()
            entry = {
                "schemaVersion": ATLauncherCache.SCHEMA_VERSION,
                "namespace": str(namespace).strip().casefold(),
                "refreshedAt": now,
                "expiresAt": now + max(0, int(ttl_seconds)),
                "payload": payload,
            }
            ATLauncherCache._write_json_atomic(path, entry)
            index.setdefault("entries", {})[cache_key] = {
                "namespace": entry["namespace"],
                "refreshedAt": now,
                "lastAccessedAt": now,
                "size": ATLauncherCache._safe_size(path),
            }
            provider = index.setdefault("provider", {})
            provider["lastSuccessfulRefreshAt"] = now
            provider["lastRefreshError"] = ""
            ATLauncherCache._recalculate(index)
            ATLauncherCache._evict(index)
            ATLauncherCache._write_index(index)
            return ATLauncherCacheLookup(payload=payload, cache_info=ATLauncherCache._info(index, now, False, False, 0))

    @staticmethod
    def record_failure(message: str) -> None:
        with ATLauncherCache._lock:
            index = ATLauncherCache._load_index()
            index.setdefault("provider", {})["lastRefreshError"] = str(message).strip()[:500]
            ATLauncherCache._write_index(index)

    @staticmethod
    def status() -> ATLauncherCacheInfo:
        with ATLauncherCache._lock:
            index = ATLauncherCache._load_index()
            provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
            refreshed = float(provider.get("lastSuccessfulRefreshAt", 0) or 0)
            age = max(0, int(time() - refreshed)) if refreshed > 0 else 0
            return ATLauncherCache._info(index, refreshed, False, False, age)

    @staticmethod
    def clear() -> None:
        with ATLauncherCache._lock:
            for path in ATLauncherCache.entries_root().glob("*.json"):
                try:
                    path.unlink()
                except OSError:
                    pass
            ATLauncherCache._write_index(ATLauncherCache._empty_index())

    @staticmethod
    def _empty_index() -> dict[str, object]:
        return {
            "schemaVersion": ATLauncherCache.SCHEMA_VERSION,
            "totalSize": 0,
            "provider": {"lastSuccessfulRefreshAt": 0.0, "lastRefreshError": ""},
            "entries": {},
        }

    @staticmethod
    def _load_index() -> dict:
        data = ATLauncherCache._read_json(ATLauncherCache.index_path())
        if not isinstance(data, dict) or data.get("schemaVersion") != ATLauncherCache.SCHEMA_VERSION:
            return ATLauncherCache._empty_index()
        data.setdefault("entries", {})
        data.setdefault("provider", {})
        return data

    @staticmethod
    def _write_index(index: dict) -> None:
        ATLauncherCache._write_json_atomic(ATLauncherCache.index_path(), index)

    @staticmethod
    def _evict(index: dict) -> None:
        ATLauncherCache._recalculate(index)
        if int(index.get("totalSize", 0) or 0) <= ATLauncherCache.MAX_SIZE_BYTES:
            return
        entries = index.get("entries", {}) if isinstance(index.get("entries"), dict) else {}
        ordered = sorted(entries.items(), key=lambda item: float(item[1].get("lastAccessedAt", 0) or 0) if isinstance(item[1], dict) else 0)
        for cache_key, _ in ordered:
            ATLauncherCache._remove_entry(index, cache_key, ATLauncherCache.entries_root() / f"{cache_key}.json")
            ATLauncherCache._recalculate(index)
            if int(index.get("totalSize", 0) or 0) <= ATLauncherCache.TARGET_SIZE_BYTES:
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
            path = ATLauncherCache.entries_root() / f"{key}.json"
            if not path.exists():
                missing.append(key)
                continue
            size = ATLauncherCache._safe_size(path)
            if isinstance(metadata, dict):
                metadata["size"] = size
            total += size
        for key in missing:
            entries.pop(key, None)
        index["totalSize"] = total

    @staticmethod
    def _info(index: dict, refreshed_at: float, from_cache: bool, stale: bool, age: int) -> ATLauncherCacheInfo:
        provider = index.get("provider", {}) if isinstance(index.get("provider"), dict) else {}
        return ATLauncherCacheInfo(
            refreshed_at=ATLauncherCache._iso(refreshed_at),
            from_cache=bool(from_cache),
            stale=bool(stale),
            age_seconds=max(0, int(age)),
            last_error=str(provider.get("lastRefreshError") or ""),
            cache_size_bytes=max(0, int(index.get("totalSize", 0) or 0)),
            cache_limit_bytes=ATLauncherCache.MAX_SIZE_BYTES,
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
