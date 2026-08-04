from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.config import MODRINTH_USER_AGENT
from src.core.network.httpx_downloader import HttpDownloader


@dataclass(frozen=True, slots=True)
class CurseForgeFallbackDownload:
    url: str
    file_name: str
    size: int
    source: str


class CurseForgeDownloadFallback:
    MODRINTH_VERSION_FILES_URL = "https://api.modrinth.com/v2/version_files"

    @staticmethod
    def find_exact_hash_mirror(sha1: str, expected_name: str = "", expected_size: int = 0) -> CurseForgeFallbackDownload | None:
        normalized_hash = str(sha1).strip().lower()
        if len(normalized_hash) != 40 or any(character not in "0123456789abcdef" for character in normalized_hash):
            return None

        client = HttpDownloader.get_client()
        try:
            response = client.post(
                CurseForgeDownloadFallback.MODRINTH_VERSION_FILES_URL,
                json={"hashes": [normalized_hash], "algorithm": "sha1"},
                headers={"Accept": "application/json", "User-Agent": MODRINTH_USER_AGENT},
                timeout=15.0,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None
        version = payload.get(normalized_hash)
        if not isinstance(version, dict):
            return None

        candidates: list[CurseForgeFallbackDownload] = []
        for item in version.get("files", []):
            if not isinstance(item, dict):
                continue
            hashes = item.get("hashes") if isinstance(item.get("hashes"), dict) else {}
            if str(hashes.get("sha1") or "").strip().lower() != normalized_hash:
                continue
            url = str(item.get("url") or "").strip()
            file_name = str(item.get("filename") or "").strip()
            try:
                size = max(0, int(item.get("size", 0) or 0))
            except (TypeError, ValueError):
                size = 0
            if not url or not file_name:
                continue
            if expected_size > 0 and size > 0 and size != expected_size:
                continue
            candidates.append(CurseForgeFallbackDownload(url=url, file_name=file_name, size=size, source="modrinth-exact-sha1"))

        if not candidates:
            return None
        normalized_name = str(expected_name).strip().casefold()
        candidates.sort(key=lambda item: (item.file_name.casefold() != normalized_name if normalized_name else False, item.file_name.casefold()))
        return candidates[0]
