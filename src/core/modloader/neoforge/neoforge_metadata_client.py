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
from src.models.modloader.neoforge_loader_version import NeoForgeLoaderVersion


class NeoForgeMetadataClient:
    MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged"
    MODERN_ARTIFACT = "neoforge"
    LEGACY_ARTIFACT = "forge"
    MODERN_MAVEN_ROOT = f"{MAVEN_BASE}/{MODERN_ARTIFACT}"
    LEGACY_MAVEN_ROOT = f"{MAVEN_BASE}/{LEGACY_ARTIFACT}"
    MODERN_METADATA_URL = f"{MODERN_MAVEN_ROOT}/maven-metadata.xml"
    LEGACY_METADATA_URL = f"{LEGACY_MAVEN_ROOT}/maven-metadata.xml"
    CACHE_TTL_SECONDS = 6 * 60 * 60
    _lock = Lock()

    @staticmethod
    def list_versions(game_version: str, force_refresh: bool = False) -> list[NeoForgeLoaderVersion]:
        game = str(game_version).strip()
        if not game:
            return []
        results: list[NeoForgeLoaderVersion] = []

        if game == "1.20.1":
            prefix = f"{game}-"
            versions = NeoForgeMetadataClient._artifact_versions(NeoForgeMetadataClient.LEGACY_ARTIFACT, force_refresh=force_refresh)
            for coordinate in versions:
                if coordinate.startswith(prefix) and len(coordinate) > len(prefix):
                    results.append(
                        NeoForgeLoaderVersion(
                            minecraft_version=game,
                            neoforge_version=coordinate[len(prefix):],
                            artifact=NeoForgeMetadataClient.LEGACY_ARTIFACT,
                            coordinate_version=coordinate,
                        )
                    )
        else:
            versions = NeoForgeMetadataClient._artifact_versions(NeoForgeMetadataClient.MODERN_ARTIFACT, force_refresh=force_refresh)
            for version in versions:
                if NeoForgeMetadataClient._matches_game_version(game, version):
                    results.append(
                        NeoForgeLoaderVersion(
                            minecraft_version=game,
                            neoforge_version=version,
                            artifact=NeoForgeMetadataClient.MODERN_ARTIFACT,
                            coordinate_version=version,
                        )
                    )

        return sorted(results, key=lambda item: NeoForgeMetadataClient._version_key(item.neoforge_version), reverse=True)

    @staticmethod
    def recommended_version(game_version: str) -> str:
        versions = NeoForgeMetadataClient.list_versions(game_version)
        if not versions:
            raise RuntimeError(f"NeoForge is not available for Minecraft {game_version}.")
        return versions[0].neoforge_version

    @staticmethod
    def coordinate(game_version: str, neoforge_version: str) -> tuple[str, str]:
        game = str(game_version).strip()
        loader = str(neoforge_version).strip()
        if not game or not loader:
            raise RuntimeError("Minecraft and NeoForge versions are required.")
        if game == "1.20.1":
            prefix = f"{game}-"
            coordinate_version = loader if loader.startswith(prefix) else f"{prefix}{loader}"
            return NeoForgeMetadataClient.LEGACY_ARTIFACT, coordinate_version
        return NeoForgeMetadataClient.MODERN_ARTIFACT, loader

    @staticmethod
    def installer_url(game_version: str, neoforge_version: str) -> str:
        artifact, coordinate_version = NeoForgeMetadataClient.coordinate(game_version, neoforge_version)
        root = NeoForgeMetadataClient.LEGACY_MAVEN_ROOT if artifact == NeoForgeMetadataClient.LEGACY_ARTIFACT else NeoForgeMetadataClient.MODERN_MAVEN_ROOT
        return f"{root}/{coordinate_version}/{artifact}-{coordinate_version}-installer.jar"

    @staticmethod
    def installer_sha1(game_version: str, neoforge_version: str) -> str:
        url = NeoForgeMetadataClient.installer_url(game_version, neoforge_version) + ".sha1"
        try:
            response = HttpDownloader.get_client().get(url, timeout=20.0)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RuntimeError(f"Could not load the NeoForge installer checksum for Minecraft {game_version}, NeoForge {neoforge_version}.") from error
        value = str(response.text).strip().split()[0].lower() if str(response.text).strip() else ""
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise RuntimeError("NeoForge returned an invalid installer checksum.")
        return value

    @staticmethod
    def _artifact_versions(artifact: str, force_refresh: bool = False) -> tuple[str, ...]:
        normalized = str(artifact).strip().casefold()
        if normalized not in {NeoForgeMetadataClient.MODERN_ARTIFACT, NeoForgeMetadataClient.LEGACY_ARTIFACT}:
            raise RuntimeError(f"Unsupported NeoForge Maven artifact: {artifact}")
        metadata_url = NeoForgeMetadataClient.MODERN_METADATA_URL if normalized == NeoForgeMetadataClient.MODERN_ARTIFACT else NeoForgeMetadataClient.LEGACY_METADATA_URL
        cache_path = Paths.neoforge_root() / f"maven-metadata-{normalized}.json"
        require_game_prefix = normalized == NeoForgeMetadataClient.LEGACY_ARTIFACT
        with NeoForgeMetadataClient._lock:
            if not force_refresh:
                cached = NeoForgeMetadataClient._load_cache(cache_path, normalized)
                if cached is not None:
                    return cached
            try:
                response = HttpDownloader.get_client().get(metadata_url, timeout=30.0)
                response.raise_for_status()
                versions = NeoForgeMetadataClient._parse_metadata(response.content, require_game_prefix=require_game_prefix)
            except (httpx.HTTPError, ElementTree.ParseError, RuntimeError) as error:
                cached = NeoForgeMetadataClient._load_cache(cache_path, normalized, ignore_expiry=True)
                if cached is not None:
                    return cached
                title = "legacy 1.20.1" if normalized == NeoForgeMetadataClient.LEGACY_ARTIFACT else "modern"
                raise RuntimeError(f"Could not load {title} NeoForge versions from the official NeoForged Maven repository.") from error
            NeoForgeMetadataClient._write_cache(cache_path, normalized, versions)
            return versions

    @staticmethod
    def _parse_metadata(raw: bytes, require_game_prefix: bool) -> tuple[str, ...]:
        root = ElementTree.fromstring(raw)
        values: list[str] = []
        for element in root.findall("./versioning/versions/version"):
            value = str(element.text or "").strip()
            if not value:
                continue
            if require_game_prefix and "-" not in value:
                continue
            values.append(value)
        if not values:
            raise RuntimeError("NeoForged Maven metadata does not contain any versions.")
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _matches_game_version(game_version: str, neoforge_version: str) -> bool:
        game_numbers = NeoForgeMetadataClient._game_version_numbers(game_version)
        if game_numbers is None:
            return False
        match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", str(neoforge_version).strip())
        if match is None:
            return False
        return (int(match.group(1)), int(match.group(2))) == game_numbers

    @staticmethod
    def _game_version_numbers(game_version: str) -> tuple[int, int] | None:
        match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(game_version).strip())
        if match is None:
            return None
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3) or 0)
        if major == 1:
            return minor, patch
        return major, minor

    @staticmethod
    def _version_key(value: str) -> tuple:
        normalized = str(value).strip().casefold()
        base, separator, suffix = normalized.partition("-")
        numbers = tuple(int(part) for part in re.findall(r"\d+", base))
        release_rank = 1 if not separator else 0
        beta_rank = 1 if "beta" not in suffix else 0
        return (*numbers, release_rank, beta_rank, suffix)

    @staticmethod
    def _load_cache(path: Path, artifact: str, ignore_expiry: bool = False) -> tuple[str, ...] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("artifact") != artifact or not isinstance(data.get("versions"), list):
            return None
        if not ignore_expiry and time() - float(data.get("cachedAt", 0) or 0) > NeoForgeMetadataClient.CACHE_TTL_SECONDS:
            return None
        versions = tuple(str(item) for item in data["versions"] if str(item).strip())
        return versions or None

    @staticmethod
    def _write_cache(path: Path, artifact: str, versions: tuple[str, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "cachedAt": time(),
            "artifact": artifact,
            "versions": list(versions),
            "fingerprint": hashlib.sha1("\n".join(versions).encode(), usedforsecurity=False).hexdigest(),
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
