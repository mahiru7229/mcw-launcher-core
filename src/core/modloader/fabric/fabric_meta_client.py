from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import time
from urllib.parse import quote
import json

import httpx

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.models.modloader.fabric_component import FabricComponent
from src.models.modloader.fabric_install_metadata import FabricInstallMetadata
from src.models.modloader.fabric_loader_version import FabricLoaderVersion


class FabricMetaClient:
    BASE_URL = "https://meta.fabricmc.net/v2"
    CATALOG_CACHE_SCHEMA = 1
    INSTALL_CACHE_SCHEMA = 1
    PROFILE_CACHE_SCHEMA = 1
    CATALOG_TTL_SECONDS = 6 * 60 * 60
    _cache_locks: dict[Path, Lock] = {}
    _cache_locks_guard = Lock()

    @staticmethod
    def list_loader_versions(game_version: str, force_refresh: bool = False) -> list[FabricLoaderVersion]:
        game_version = FabricMetaClient._required_version(game_version, "Minecraft version")
        data = FabricMetaClient._load_catalog(game_version, force_refresh)
        versions: list[FabricLoaderVersion] = []

        if not isinstance(data, list):
            raise RuntimeError("Fabric Meta returned an invalid loader list.")

        for item in data:
            if not isinstance(item, dict):
                continue

            loader = item.get("loader", item)
            intermediary = item.get("intermediary", {})
            if not isinstance(loader, dict):
                continue

            version = str(loader.get("version", "")).strip()
            if not version:
                continue

            intermediary_version = str(intermediary.get("version", "")).strip() if isinstance(intermediary, dict) else ""
            versions.append(
                FabricLoaderVersion(
                    version=version,
                    stable=bool(loader.get("stable", item.get("stable", False))),
                    intermediary_version=intermediary_version,
                    loader_maven=str(loader.get("maven", "")).strip(),
                    intermediary_maven=str(intermediary.get("maven", "")).strip() if isinstance(intermediary, dict) else "",
                )
            )

        return versions

    @staticmethod
    def get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> FabricInstallMetadata:
        game_version = FabricMetaClient._required_version(game_version, "Minecraft version")
        loader_version = FabricMetaClient._required_version(loader_version, "Fabric Loader version")
        data = FabricMetaClient._load_install_metadata(game_version, loader_version, force_refresh)

        if not isinstance(data, dict):
            raise RuntimeError("Fabric Meta returned invalid installation metadata.")

        loader = data.get("loader")
        intermediary = data.get("intermediary")
        launcher_meta = data.get("launcherMeta")
        if not isinstance(loader, dict) or not isinstance(intermediary, dict) or not isinstance(launcher_meta, dict):
            raise RuntimeError("Fabric installation metadata is incomplete.")

        resolved_loader_version = str(loader.get("version", "")).strip()
        intermediary_version = str(intermediary.get("version", "")).strip()
        loader_maven = str(loader.get("maven", "")).strip()
        intermediary_maven = str(intermediary.get("maven", "")).strip()
        main_classes = launcher_meta.get("mainClass", {})
        main_class = str(main_classes.get("client", "")).strip() if isinstance(main_classes, dict) else ""

        if resolved_loader_version != loader_version:
            raise RuntimeError(f"Fabric Meta resolved Loader {resolved_loader_version or 'unknown'} instead of {loader_version}.")
        if not intermediary_version or not loader_maven or not intermediary_maven or not main_class:
            raise RuntimeError("Fabric installation metadata is missing a required component.")

        libraries_data = launcher_meta.get("libraries", {})
        libraries: list[dict] = []
        if isinstance(libraries_data, dict):
            for group in ("common", "client"):
                values = libraries_data.get(group, [])
                if isinstance(values, list):
                    libraries.extend(item for item in values if isinstance(item, dict))

        return FabricInstallMetadata(
            game=FabricComponent(uid="net.minecraft", version=game_version),
            intermediary=FabricComponent(uid="net.fabricmc.intermediary", version=intermediary_version, maven=intermediary_maven),
            loader=FabricComponent(uid="net.fabricmc.fabric-loader", version=resolved_loader_version, maven=loader_maven),
            main_class=main_class,
            libraries=tuple(libraries),
        )

    @staticmethod
    def get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict:
        game_version = FabricMetaClient._required_version(game_version, "Minecraft version")
        loader_version = FabricMetaClient._required_version(loader_version, "Fabric Loader version")
        data = FabricMetaClient._load_profile(game_version, loader_version, force_refresh)
        if not isinstance(data, dict) or not data.get("mainClass"):
            raise RuntimeError(f"Fabric profile is unavailable for Minecraft {game_version} and Loader {loader_version}.")
        return data

    @staticmethod
    def clear_cached_install(game_version: str, loader_version: str) -> None:
        for path in (
            Paths.fabric_install_metadata_json(game_version, loader_version),
            Paths.fabric_profile_json(game_version, loader_version),
        ):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _load_catalog(game_version: str, force_refresh: bool) -> object:
        path = Paths.fabric_catalog_json(game_version)
        with FabricMetaClient._get_cache_lock(path):
            cached = FabricMetaClient._read_cache(path, FabricMetaClient.CATALOG_CACHE_SCHEMA, gameVersion=game_version)
            if cached is not None and not force_refresh:
                try:
                    fetched_at = float(cached.get("fetchedAt", 0) or 0)
                except (TypeError, ValueError):
                    fetched_at = 0
                if time() - fetched_at <= FabricMetaClient.CATALOG_TTL_SECONDS:
                    return cached.get("payload")

            encoded_game = quote(game_version, safe="")
            return FabricMetaClient._refresh_with_fallback(
                path=path,
                schema=FabricMetaClient.CATALOG_CACHE_SCHEMA,
                identity={"gameVersion": game_version},
                request_path=f"/versions/loader/{encoded_game}",
                cached=cached,
            )

    @staticmethod
    def _load_install_metadata(game_version: str, loader_version: str, force_refresh: bool) -> object:
        path = Paths.fabric_install_metadata_json(game_version, loader_version)
        with FabricMetaClient._get_cache_lock(path):
            identity = {"gameVersion": game_version, "loaderVersion": loader_version}
            cached = FabricMetaClient._read_cache(path, FabricMetaClient.INSTALL_CACHE_SCHEMA, **identity)
            if cached is not None and not force_refresh:
                return cached.get("payload")

            encoded_game = quote(game_version, safe="")
            encoded_loader = quote(loader_version, safe="")
            return FabricMetaClient._refresh_with_fallback(
                path=path,
                schema=FabricMetaClient.INSTALL_CACHE_SCHEMA,
                identity=identity,
                request_path=f"/versions/loader/{encoded_game}/{encoded_loader}",
                cached=cached,
            )

    @staticmethod
    def _load_profile(game_version: str, loader_version: str, force_refresh: bool) -> object:
        path = Paths.fabric_profile_json(game_version, loader_version)
        with FabricMetaClient._get_cache_lock(path):
            identity = {"gameVersion": game_version, "loaderVersion": loader_version}
            cached = FabricMetaClient._read_cache(path, FabricMetaClient.PROFILE_CACHE_SCHEMA, **identity)
            if cached is not None and not force_refresh:
                return cached.get("payload")

            encoded_game = quote(game_version, safe="")
            encoded_loader = quote(loader_version, safe="")
            return FabricMetaClient._refresh_with_fallback(
                path=path,
                schema=FabricMetaClient.PROFILE_CACHE_SCHEMA,
                identity=identity,
                request_path=f"/versions/loader/{encoded_game}/{encoded_loader}/profile/json",
                cached=cached,
            )

    @staticmethod
    def _get_cache_lock(path: Path) -> Lock:
        try:
            normalized = path.resolve(strict=False)
        except OSError:
            normalized = path.absolute()
        with FabricMetaClient._cache_locks_guard:
            return FabricMetaClient._cache_locks.setdefault(normalized, Lock())

    @staticmethod
    def _refresh_with_fallback(path: Path, schema: int, identity: dict[str, str], request_path: str, cached: dict | None) -> object:
        try:
            payload = FabricMetaClient._get_json(request_path)
        except RuntimeError:
            if cached is not None:
                return cached.get("payload")
            raise

        FabricMetaClient._write_cache(path, schema, identity, payload)
        return payload

    @staticmethod
    def _get_json(path: str) -> object:
        client = HttpDownloader.get_client()
        try:
            response = client.get(FabricMetaClient.BASE_URL + path, timeout=20.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Unable to contact Fabric Meta and no cached metadata is available.") from error

    @staticmethod
    def _read_cache(path: Path, schema: int, **identity: str) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        if not isinstance(data, dict) or data.get("schemaVersion") != schema:
            return None
        if any(data.get(key) != value for key, value in identity.items()):
            return None
        if "payload" not in data:
            return None
        return data

    @staticmethod
    def _write_cache(path: Path, schema: int, identity: dict[str, str], payload: object) -> None:
        data = {"schemaVersion": schema, "fetchedAt": time(), **identity, "payload": payload}
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".part")
        temp_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _required_version(value: str, label: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise RuntimeError(f"{label} is required.")
        return normalized
