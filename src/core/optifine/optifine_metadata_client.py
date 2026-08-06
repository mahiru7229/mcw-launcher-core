from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import time

from src.config import VERSION_ID
from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.core.optifine.optifine_metadata_parser import OptiFineMetadataParser
from src.models.optifine.optifine_models import OptiFineVersion


class OptiFineMetadataClient:
    DOWNLOADS_URL = "https://optifine.net/downloads"
    CACHE_TTL_SECONDS = 6 * 60 * 60
    USER_AGENT = f"MCW-Launcher/{VERSION_ID}"

    @classmethod
    def list_versions(cls, minecraft_version: str = "", include_preview: bool = False, force_refresh: bool = False) -> list[OptiFineVersion]:
        requested = str(minecraft_version or "").strip()
        cached, fresh = cls._read_cache()
        versions = cached
        if force_refresh or not fresh:
            try:
                response = HttpDownloader.get_client().get(cls.DOWNLOADS_URL, headers={"User-Agent": cls.USER_AGENT, "Accept": "text/html"}, timeout=25.0)
                response.raise_for_status()
                parsed = OptiFineMetadataParser.parse(response.text)
                if not parsed:
                    raise RuntimeError("The official OptiFine download page did not contain a recognizable version list.")
                versions = parsed
                cls._write_cache(parsed)
            except Exception:
                if not cached:
                    raise
                versions = cached
        return [item for item in versions if (not requested or item.minecraft_version == requested) and (include_preview or not item.preview)]

    @staticmethod
    def official_downloads_url() -> str:
        return OptiFineMetadataClient.DOWNLOADS_URL

    @staticmethod
    def _cache_path() -> Path:
        return Paths.optifine_metadata_cache()

    @classmethod
    def _read_cache(cls) -> tuple[list[OptiFineVersion], bool]:
        path = cls._cache_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(payload.get("fetchedAtEpoch", 0.0) or 0.0)
            raw_versions = payload.get("versions", [])
            versions = [OptiFineVersion(**raw) for raw in raw_versions if isinstance(raw, dict)]
            return versions, bool(versions and (time.time() - fetched_at) <= cls.CACHE_TTL_SECONDS)
        except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
            return [], False

    @classmethod
    def _write_cache(cls, versions: list[OptiFineVersion]) -> None:
        path = cls._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "fetchedAtEpoch": time.time(),
            "source": cls.DOWNLOADS_URL,
            "versions": [asdict(item) for item in versions],
        }
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
