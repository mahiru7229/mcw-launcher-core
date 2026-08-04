from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import time
from xml.etree import ElementTree
import hashlib
import json
import re

import httpx

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.models.modloader.forge_loader_version import ForgeLoaderVersion


class ForgeMetadataClient:
    MAVEN_ROOT = "https://maven.minecraftforge.net/net/minecraftforge/forge"
    METADATA_URL = f"{MAVEN_ROOT}/maven-metadata.xml"
    CACHE_TTL_SECONDS = 6 * 60 * 60
    _lock = Lock()

    @staticmethod
    def list_versions(game_version: str, force_refresh: bool = False) -> list[ForgeLoaderVersion]:
        game = str(game_version).strip()
        if not game:
            return []
        versions = ForgeMetadataClient._all_versions(force_refresh=force_refresh)
        prefix = f"{game}-"
        results = [ForgeLoaderVersion(game, item[len(prefix):]) for item in versions if item.startswith(prefix)]
        return sorted(results, key=lambda item: ForgeMetadataClient._version_key(item.forge_version), reverse=True)

    @staticmethod
    def recommended_version(game_version: str) -> str:
        versions = ForgeMetadataClient.list_versions(game_version)
        if not versions:
            raise RuntimeError(f"Minecraft Forge is not available for Minecraft {game_version}.")
        return versions[0].forge_version

    @staticmethod
    def installer_url(game_version: str, forge_version: str) -> str:
        coordinate = f"{game_version}-{forge_version}"
        return f"{ForgeMetadataClient.MAVEN_ROOT}/{coordinate}/forge-{coordinate}-installer.jar"

    @staticmethod
    def installer_sha1(game_version: str, forge_version: str) -> str:
        url = ForgeMetadataClient.installer_url(game_version, forge_version) + ".sha1"
        try:
            response = HttpDownloader.get_client().get(url, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Could not load the Forge installer checksum for {game_version}-{forge_version}.") from error
        value = str(response.text).strip().split()[0].lower() if str(response.text).strip() else ""
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise RuntimeError("Forge returned an invalid installer checksum.")
        return value

    @staticmethod
    def _all_versions(force_refresh: bool = False) -> tuple[str, ...]:
        cache_path = Paths.forge_root() / "maven-metadata.json"
        with ForgeMetadataClient._lock:
            if not force_refresh:
                cached = ForgeMetadataClient._load_cache(cache_path)
                if cached is not None:
                    return cached
            try:
                response = HttpDownloader.get_client().get(ForgeMetadataClient.METADATA_URL, timeout=30.0)
                response.raise_for_status()
                versions = ForgeMetadataClient._parse_metadata(response.content)
            except (httpx.HTTPError, ElementTree.ParseError, RuntimeError) as error:
                cached = ForgeMetadataClient._load_cache(cache_path, ignore_expiry=True)
                if cached is not None:
                    return cached
                raise RuntimeError("Could not load Minecraft Forge versions from the official Forge Maven repository.") from error
            ForgeMetadataClient._write_cache(cache_path, versions)
            return versions

    @staticmethod
    def _parse_metadata(raw: bytes) -> tuple[str, ...]:
        root = ElementTree.fromstring(raw)
        values = []
        for element in root.findall("./versioning/versions/version"):
            value = str(element.text or "").strip()
            if value and "-" in value:
                values.append(value)
        if not values:
            raise RuntimeError("Forge Maven metadata does not contain any versions.")
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _version_key(value: str) -> tuple:
        parts = re.split(r"([0-9]+)", str(value))
        return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)

    @staticmethod
    def _load_cache(path: Path, ignore_expiry: bool = False) -> tuple[str, ...] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
            return None
        if not ignore_expiry and time() - float(data.get("cachedAt", 0) or 0) > ForgeMetadataClient.CACHE_TTL_SECONDS:
            return None
        values = tuple(str(item) for item in data["versions"] if str(item).strip())
        return values or None

    @staticmethod
    def _write_cache(path: Path, versions: tuple[str, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schemaVersion": 1, "cachedAt": time(), "versions": list(versions), "fingerprint": hashlib.sha1("\n".join(versions).encode(), usedforsecurity=False).hexdigest()}
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
