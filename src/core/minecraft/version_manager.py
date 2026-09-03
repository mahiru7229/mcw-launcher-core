from __future__ import annotations

import json
from pathlib import Path

from src.core.fs.paths import Paths
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.version import Version
from src.models.minecraft.version_manifest import VersionManifest


class VersionManager:
    @staticmethod
    def load(version_id: str | None = None) -> Version:
        """Load a Minecraft version without performing I/O at import time."""
        selected_id = str(version_id or "").strip()
        if not selected_id:
            selected_id = VersionManifestManager.latest_version()
        if not selected_id:
            raise RuntimeError("Minecraft did not report a latest release version.")

        version_path = VersionManager._download_version(
            VersionManager._choosing_version(selected_id)
        )

        if version_path is None:
            raise RuntimeError(f"Cannot load metadata for Minecraft {selected_id}.")

        version_data = VersionManager._load_version(version_path)
        version = VersionManager._parse_version(version_data, version_path)
        if version is None:
            raise RuntimeError(f"Invalid metadata for Minecraft version '{selected_id}'.")
        return version

    @staticmethod
    def _choosing_version(version_id: str) -> VersionManifest:
        versions = VersionManifestManager.get()
        version = next((version for version in versions if version.id == version_id), None)
        if version is None:
            raise RuntimeError(f"Minecraft version '{version_id}' was not found in the manifest.")
        return version

    @staticmethod
    def _download_version(version: VersionManifest) -> Path | None:
        version_path = Paths.version_json(version)
        version_path.parent.mkdir(parents=True, exist_ok=True)
        if VersionManager._cached_metadata_is_valid(version_path, version):
            return version_path
        try:
            return HttpDownloader.download(
                download_info=version,
                path=version_path,
                max_retry=3,
                timeout=20.0,
            )
        except Exception:
            if VersionManager._cached_metadata_is_valid(version_path, version):
                return version_path
            return None

    @staticmethod
    def _cached_metadata_is_valid(path: Path, version: VersionManifest) -> bool:
        if not path.is_file() or not version.sha1:
            return False
        if version.size > 0 and path.stat().st_size != version.size:
            return False
        return HttpDownloader.verify_sha1(path, version.sha1)

    @staticmethod
    def _load_version(path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _parse_version(version_data: dict, version_path: Path) -> Version | None:
        try:
            return Version(
                id=version_data["id"],
                arguments=version_data.get("arguments"),
                minecraft_arguments=version_data.get(
                    "minecraftArguments"
                ),
                libraries=version_data["libraries"],
                downloads=version_data["downloads"],
                asset_index=version_data["assetIndex"],
                assets= version_data["assets"],
                main_class=version_data["mainClass"],
                java_version=version_data.get("javaVersion", {"component": "jre-legacy","majorVersion": 8,}),
                raw_json=version_data,
                path=version_path,
                type=version_data.get("type", "release"),
            )
        except (KeyError, TypeError, ValueError):
            return None
