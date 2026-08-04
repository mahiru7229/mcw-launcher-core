from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.core.update.versioning import LauncherVersion
from src.models.update.update_info import ReleaseAsset, UpdateInfo


class GitHubReleaseClient:
    API_ROOT = "https://api.github.com"
    CACHE_SCHEMA_VERSION = 1
    CACHE_TTL_SECONDS = 15 * 60

    def __init__(self, repository: str, current_version: str, channel: str = "stable", cache_path: Path | None = None) -> None:
        repository_name = str(repository).strip().strip("/")
        if repository_name.count("/") != 1:
            raise ValueError("GitHub repository must use the 'owner/name' format.")

        self.repository = repository_name
        self.current_version = str(current_version).strip()
        self.channel = str(channel).strip().lower() or "beta"
        self.cache_path = Path(cache_path) if cache_path is not None else Paths.update_release_cache()

    def check(self, force_refresh: bool = False) -> UpdateInfo | None:
        releases = self._load_releases(force_refresh=force_refresh)
        return self._select_update(releases)

    def _load_releases(self, force_refresh: bool) -> list[dict[str, Any]]:
        cached = self._read_cache()
        if not force_refresh and cached is not None and not self._cache_expired(cached):
            payload = cached.get("releases")
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]

        try:
            releases = self._fetch_releases()
        except Exception:
            if cached is not None:
                payload = cached.get("releases")
                if isinstance(payload, list):
                    return [item for item in payload if isinstance(item, dict)]
            raise

        self._write_cache(releases)
        return releases

    def _fetch_releases(self) -> list[dict[str, Any]]:
        client = HttpDownloader.get_client()
        response = client.get(
            f"{self.API_ROOT}/repos/{self.repository}/releases",
            params={"per_page": 30},
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"{self.repository}/{self.current_version}",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("GitHub returned an invalid releases response.")
        return [item for item in payload if isinstance(item, dict)]

    def _select_update(self, releases: list[dict[str, Any]]) -> UpdateInfo | None:
        current = LauncherVersion.parse(self.current_version)
        candidates: list[tuple[LauncherVersion, dict[str, Any], ReleaseAsset]] = []

        for release in releases:
            if release.get("draft") is True:
                continue
            prerelease = bool(release.get("prerelease"))
            if self.channel == "stable" and prerelease:
                continue

            tag_name = str(release.get("tag_name") or "").strip()
            try:
                version = LauncherVersion.parse(tag_name)
            except ValueError:
                continue
            if self.channel == "beta" and version.prerelease in {"alpha", "pre"}:
                continue
            if version <= current:
                continue

            asset = self._select_asset(release.get("assets"))
            if asset is None:
                continue
            candidates.append((version, release, asset))

        if not candidates:
            return None

        version, release, asset = max(candidates, key=lambda item: item[0].comparison_key())
        return UpdateInfo(
            current_version=self.current_version,
            version=str(version),
            tag_name=str(release.get("tag_name") or version),
            title=str(release.get("name") or release.get("tag_name") or version),
            release_notes=str(release.get("body") or "").strip(),
            release_url=str(release.get("html_url") or ""),
            published_at=str(release.get("published_at") or release.get("created_at") or ""),
            prerelease=bool(release.get("prerelease")),
            asset=asset,
        )

    @staticmethod
    def _select_asset(raw_assets: object) -> ReleaseAsset | None:
        if not isinstance(raw_assets, list):
            return None

        scored: list[tuple[int, dict[str, Any]]] = []
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, dict):
                continue
            name = str(raw_asset.get("name") or "").strip()
            download_url = str(raw_asset.get("browser_download_url") or "").strip()
            if not name.lower().endswith(".zip") or not download_url.startswith("https://"):
                continue

            lowered = name.casefold()
            score = 0
            if "windows" in lowered:
                score += 8
            elif "win" in lowered:
                score += 6
            if "x64" in lowered or "amd64" in lowered:
                score += 4
            if "mcw" in lowered or "launcher" in lowered:
                score += 2
            scored.append((score, raw_asset))

        if not scored:
            return None

        raw_asset = max(scored, key=lambda item: item[0])[1]
        digest = str(raw_asset.get("digest") or "").strip().lower()
        sha256 = digest.removeprefix("sha256:") if digest.startswith("sha256:") and len(digest) == 71 else None
        return ReleaseAsset(
            name=str(raw_asset.get("name") or "update.zip"),
            download_url=str(raw_asset.get("browser_download_url") or ""),
            size=max(0, int(raw_asset.get("size") or 0)),
            sha256=sha256,
        )

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != self.CACHE_SCHEMA_VERSION:
            return None
        if payload.get("repository") != self.repository:
            return None
        return payload

    def _write_cache(self, releases: list[dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_name(f"{self.cache_path.name}.tmp")
        payload = {
            "schema_version": self.CACHE_SCHEMA_VERSION,
            "repository": self.repository,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "releases": releases,
        }
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(self.cache_path)

    def _cache_expired(self, payload: dict[str, Any]) -> bool:
        fetched_at = payload.get("fetched_at")
        if not isinstance(fetched_at, str):
            return True
        try:
            timestamp = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        return age.total_seconds() >= self.CACHE_TTL_SECONDS
