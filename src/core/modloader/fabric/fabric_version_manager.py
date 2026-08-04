from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Lock
import hashlib
import json

import httpx

from src.core.fs.paths import Paths
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.fabric.fabric_meta_client import FabricMetaClient
from src.core.modloader.fabric.maven_artifact import MavenArtifact
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.minecraft.version import Version
from src.models.modloader.fabric_install_metadata import FabricInstallMetadata
from src.models.progress.progress_stage import ProgressStage


class FabricVersionManager:
    CACHE_SCHEMA_VERSION = 2
    _locks: dict[str, Lock] = {}
    _locks_guard = Lock()

    @staticmethod
    def load(game_version: str, loader_version: str, reporter: ProgressReporter | None = None) -> Version:
        base_version = VersionManager.load(game_version)
        return FabricVersionManager.install(base_version, loader_version, reporter)

    @staticmethod
    def recommended_loader_version(game_version: str) -> str:
        versions = FabricMetaClient.list_loader_versions(game_version)
        if not versions:
            raise RuntimeError(f"Fabric Loader is not available for Minecraft {game_version}.")

        recommended = next((version for version in versions if version.stable), None)
        if recommended is None:
            raise RuntimeError(
                f"No stable Fabric Loader is available for Minecraft {game_version}. "
                "Choose an experimental Loader version manually from Manage selected instance."
            )
        return recommended.version

    @staticmethod
    def install(base_version: Version, loader_version: str, reporter: ProgressReporter | None = None, force_refresh: bool = False, repair_libraries: bool = False) -> Version:
        loader_version = loader_version.strip()
        if not loader_version:
            raise RuntimeError("Select a Fabric Loader version.")

        cache_path = Paths.fabric_version_json(base_version.id, loader_version)
        lock = FabricVersionManager._get_lock(f"{base_version.id}:{loader_version}")

        with lock:
            if not force_refresh:
                cached = FabricVersionManager._load_cached(cache_path, base_version.raw_json, base_version.id, loader_version)
                if cached is not None:
                    cached_version = VersionManager._parse_version(cached, cache_path)
                    if cached_version is not None:
                        return cached_version

            if reporter is not None:
                action = "Repairing" if force_refresh else "Installing"
                reporter.status(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"{action} Fabric Loader {loader_version}...")

            metadata = FabricMetaClient.get_install_metadata(base_version.id, loader_version, force_refresh=force_refresh)
            profile = FabricMetaClient.get_profile(base_version.id, loader_version, force_refresh=force_refresh)
            normalized_profile = FabricVersionManager._normalize_profile_libraries(profile, reporter=reporter, force_artifact_refresh=repair_libraries)
            merged = FabricVersionManager._merge_profiles(base_version.raw_json, normalized_profile, metadata)
            FabricVersionManager._write_json(cache_path, merged)
            version = VersionManager._parse_version(merged, cache_path)

            if version is None:
                raise RuntimeError("Fabric version metadata could not be parsed.")
            return version

    @staticmethod
    def repair(base_version: Version, loader_version: str, reporter: ProgressReporter | None = None) -> Version:
        cache_path = Paths.fabric_version_json(base_version.id, loader_version)
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass
        return FabricVersionManager.install(
            base_version=base_version,
            loader_version=loader_version,
            reporter=reporter,
            force_refresh=True,
            repair_libraries=True,
        )

    @staticmethod
    def components(version: Version) -> tuple[dict, ...]:
        fabric_data = (getattr(version, "raw_json", {}) or {}).get("fabric", {})
        components = fabric_data.get("components", []) if isinstance(fabric_data, dict) else []
        return tuple(item for item in components if isinstance(item, dict))

    @staticmethod
    def _get_lock(key: str) -> Lock:
        with FabricVersionManager._locks_guard:
            return FabricVersionManager._locks.setdefault(key, Lock())

    @staticmethod
    def _load_cached(path: Path, base: dict, game_version: str, loader_version: str) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        fabric_data = data.get("fabric", {})
        if not isinstance(fabric_data, dict):
            return None
        if fabric_data.get("schemaVersion") != FabricVersionManager.CACHE_SCHEMA_VERSION:
            return None
        if data.get("inheritsFrom") != game_version:
            return None
        if fabric_data.get("gameVersion") != game_version or fabric_data.get("loaderVersion") != loader_version:
            return None
        if fabric_data.get("baseFingerprint") != FabricVersionManager._fingerprint(base):
            return None
        if not fabric_data.get("intermediaryVersion") or not fabric_data.get("components"):
            return None
        if not data.get("mainClass") or not data.get("libraries"):
            return None
        return data

    @staticmethod
    def _normalize_profile_libraries(profile: dict, reporter: ProgressReporter | None = None, force_artifact_refresh: bool = False) -> dict:
        normalized = deepcopy(profile)
        normalized_libraries: list[dict] = []

        for library in profile.get("libraries", []):
            if not isinstance(library, dict):
                continue

            item = deepcopy(library)
            artifact_data = item.get("downloads", {}).get("artifact")
            if FabricVersionManager._valid_artifact_data(artifact_data):
                normalized_libraries.append(item)
                continue

            coordinate = str(item.get("name", "")).strip()
            repository_url = str(item.get("url") or "https://maven.fabricmc.net/")
            artifact = MavenArtifact.from_coordinate(coordinate, repository_url)
            if reporter is None:
                sha1, size = FabricVersionManager._load_artifact_metadata(artifact, force_artifact_refresh)
            else:
                sha1, size = FabricVersionManager._load_artifact_metadata(artifact, force_artifact_refresh, reporter)
            item["downloads"] = {
                "artifact": {
                    "path": artifact.path.as_posix(),
                    "sha1": sha1,
                    "size": size,
                    "url": artifact.url,
                }
            }
            normalized_libraries.append(item)

        normalized["libraries"] = normalized_libraries
        return normalized

    @staticmethod
    def _valid_artifact_data(value: object) -> bool:
        if not isinstance(value, dict) or "size" not in value:
            return False
        sha1 = str(value.get("sha1", "")).strip().lower()
        try:
            size = int(value.get("size", 0))
        except (TypeError, ValueError):
            return False
        return bool(value.get("path") and value.get("url") and size >= 0 and len(sha1) == 40 and all(character in "0123456789abcdef" for character in sha1))

    @staticmethod
    def _load_artifact_metadata(artifact: MavenArtifact, force_artifact_refresh: bool = False, reporter: ProgressReporter | None = None) -> tuple[str, int]:
        client = HttpDownloader.get_client()
        sha1 = ""

        try:
            sha1_response = client.get(artifact.url + ".sha1", timeout=20.0)
            sha1_response.raise_for_status()
            sha1 = sha1_response.text.strip().split()[0].lower()
        except (httpx.HTTPError, IndexError):
            sha1 = ""

        if len(sha1) == 40 and all(character in "0123456789abcdef" for character in sha1):
            size = 0
            try:
                response = client.head(artifact.url, timeout=20.0)
                response.raise_for_status()
                size = int(response.headers.get("Content-Length", 0) or 0)
            except (httpx.HTTPError, ValueError):
                size = 0
            return sha1, size

        library_path = Paths.libraries() / artifact.path
        _, calculated_sha1, size = HttpDownloader.download_and_hash(
            url=artifact.url,
            path=library_path,
            max_retry=3,
            force=force_artifact_refresh,
            reporter=reporter,
            progress_stage=ProgressStage.INSTALLING_MOD_LOADER,
            progress_message=f"Downloading Fabric library {artifact.path.name}...",
        )
        return calculated_sha1, size

    @staticmethod
    def _merge_profiles(base: dict, fabric: dict, metadata: FabricInstallMetadata) -> dict:
        merged = deepcopy(base)
        game_version = metadata.game.version
        loader_version = metadata.loader.version
        profile_id = str(fabric.get("id") or f"fabric-loader-{loader_version}-{game_version}")
        profile_main_class = str(fabric.get("mainClass", "")).strip()

        if profile_main_class != metadata.main_class:
            raise RuntimeError("Fabric profile main class does not match its installation metadata.")

        merged["id"] = profile_id
        merged["inheritsFrom"] = game_version
        merged["mainClass"] = profile_main_class
        merged["type"] = fabric.get("type", base.get("type", "release"))
        merged["libraries"] = FabricVersionManager._merge_libraries(base.get("libraries", []), fabric.get("libraries", []))
        merged["arguments"] = FabricVersionManager._merge_arguments(base.get("arguments"), fabric.get("arguments"))

        base_legacy = str(base.get("minecraftArguments", "")).strip()
        fabric_legacy = str(fabric.get("minecraftArguments", "")).strip()
        if base_legacy or fabric_legacy:
            merged["minecraftArguments"] = " ".join(value for value in (base_legacy, fabric_legacy) if value)

        components = [
            {"uid": metadata.game.uid, "version": metadata.game.version},
            {"uid": metadata.intermediary.uid, "version": metadata.intermediary.version, "maven": metadata.intermediary.maven},
            {"uid": metadata.loader.uid, "version": metadata.loader.version, "maven": metadata.loader.maven},
        ]
        merged["fabric"] = {
            "schemaVersion": FabricVersionManager.CACHE_SCHEMA_VERSION,
            "gameVersion": game_version,
            "loaderVersion": loader_version,
            "intermediaryVersion": metadata.intermediary.version,
            "profileId": profile_id,
            "baseFingerprint": FabricVersionManager._fingerprint(base),
            "components": components,
        }
        return merged

    @staticmethod
    def _merge_libraries(base_libraries: list, fabric_libraries: list) -> list:
        merged: list[dict] = []
        indexes: dict[str, int] = {}

        for library in [*base_libraries, *fabric_libraries]:
            if not isinstance(library, dict):
                continue
            key = FabricVersionManager._library_key(str(library.get("name", "")))
            if key and key in indexes:
                merged[indexes[key]] = deepcopy(library)
                continue
            if key:
                indexes[key] = len(merged)
            merged.append(deepcopy(library))

        return merged

    @staticmethod
    def _library_key(coordinate: str) -> str:
        base_coordinate = coordinate.split("@", 1)[0]
        parts = base_coordinate.split(":")
        if len(parts) < 3:
            return coordinate
        group, artifact = parts[:2]
        classifier = parts[3] if len(parts) > 3 else ""
        return ":".join((group, artifact, classifier))

    @staticmethod
    def _merge_arguments(base_arguments: object, fabric_arguments: object) -> dict:
        base = deepcopy(base_arguments) if isinstance(base_arguments, dict) else {}
        fabric = fabric_arguments if isinstance(fabric_arguments, dict) else {}
        return {
            "jvm": [*base.get("jvm", []), *fabric.get("jvm", [])],
            "game": [*base.get("game", []), *fabric.get("game", [])],
        }

    @staticmethod
    def _fingerprint(data: dict) -> str:
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".part")
        temp_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)
