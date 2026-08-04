from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os

import requests

from src.core.fs.paths import Paths
from src.models.minecraft.version_manifest import VersionManifest


MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


class VersionManifestManager:
    @staticmethod
    def get() -> list[VersionManifest]:
        manifest_path = VersionManifestManager._download_manifest()
        manifest_data = VersionManifestManager._load_manifest(manifest_path)
        return VersionManifestManager._parse_manifest(manifest_data)

    @staticmethod
    def _download_manifest() -> Path | None:
        manifest_path = Paths.version_manifest()
        manifest_path.parent.mkdir(exist_ok=True, parents=True)
        temporary_path = manifest_path.with_name(f"{manifest_path.name}.tmp")

        try:
            response = requests.get(MANIFEST_URL, timeout=10)
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                raise_for_status()

            response_text = str(response.text)
            payload = json.loads(response_text)
            if not isinstance(payload, dict) or not isinstance(payload.get("versions"), list):
                raise ValueError("Mojang returned an invalid version manifest.")

            with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
                file.write(response_text)
                file.flush()
                os.fsync(file.fileno())
            temporary_path.replace(manifest_path)
            return manifest_path
        except (requests.RequestException, OSError, UnicodeError, json.JSONDecodeError, ValueError):
            temporary_path.unlink(missing_ok=True)
            return manifest_path if manifest_path.is_file() else None

    @staticmethod
    def _load_manifest(path: Path | None) -> dict:
        if path is None:
            return {}
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def latest_version(is_snapshot: bool = False) -> str:
        manifest_path = VersionManifestManager._download_manifest()
        manifest_data = VersionManifestManager._load_manifest(manifest_path)
        latest = manifest_data.get("latest")
        if not isinstance(latest, dict):
            return ""
        key = "snapshot" if is_snapshot else "release"
        value = latest.get(key)
        return str(value).strip() if isinstance(value, str) else ""

    @staticmethod
    def _parse_manifest(manifest: dict) -> list[VersionManifest]:
        if not isinstance(manifest, dict):
            return []
        versions = manifest.get("versions")
        if not isinstance(versions, list):
            return []

        parsed: list[VersionManifest] = []
        try:
            for version in versions:
                if not isinstance(version, dict):
                    return []
                parsed.append(VersionManifest(id=str(version["id"]), type=str(version["type"]), url=str(version["url"]), release_time=datetime.fromisoformat(str(version["releaseTime"]))))
        except (KeyError, TypeError, ValueError):
            return []
        return parsed
