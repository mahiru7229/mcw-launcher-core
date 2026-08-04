from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import time
from urllib.parse import quote
import json
import re

import httpx

from src.core.fs.paths import Paths
from src.core.network.httpx_downloader import HttpDownloader
from src.models.modloader.quilt_component import QuiltComponent
from src.models.modloader.quilt_install_metadata import QuiltInstallMetadata
from src.models.modloader.quilt_loader_version import QuiltLoaderVersion


class QuiltMetaClient:
    BASE_URL = "https://meta.quiltmc.org/v3"
    CATALOG_CACHE_SCHEMA = 2
    INSTALL_CACHE_SCHEMA = 1
    PROFILE_CACHE_SCHEMA = 1
    CATALOG_TTL_SECONDS = 6 * 60 * 60
    _cache_locks: dict[Path, Lock] = {}
    _cache_locks_guard = Lock()

    @staticmethod
    def list_loader_versions(game_version: str, force_refresh: bool = False) -> list[QuiltLoaderVersion]:
        game_version = QuiltMetaClient._required_version(game_version, "Minecraft version")
        data = QuiltMetaClient._load_catalog(game_version, force_refresh)
        if not isinstance(data, list):
            raise RuntimeError("Quilt Meta returned an invalid loader list.")

        versions_by_id: dict[str, QuiltLoaderVersion] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            loader = item.get("loader", item)
            mappings = QuiltMetaClient._mappings_component(item)
            if not isinstance(loader, dict):
                continue
            version = str(loader.get("version", "")).strip()
            if not version:
                continue
            parsed = QuiltLoaderVersion(
                version=version,
                stable=QuiltMetaClient._stable_flag(loader, item, version),
                mappings_version=str(mappings.get("version", "")).strip() if isinstance(mappings, dict) else "",
                loader_maven=str(loader.get("maven", "")).strip(),
                mappings_maven=str(mappings.get("maven", "")).strip() if isinstance(mappings, dict) else "",
            )
            current = versions_by_id.get(version)
            if current is None or (parsed.stable and not current.stable):
                versions_by_id[version] = parsed
        return sorted(versions_by_id.values(), key=lambda entry: QuiltMetaClient.version_sort_key(entry.version), reverse=True)


    @staticmethod
    def _stable_flag(loader: dict, item: dict, version: str) -> bool:
        for source in (loader, item):
            value = source.get("stable")
            if isinstance(value, bool):
                return value
        without_build = str(version).strip().split("+", 1)[0]
        return "-" not in without_build

    @staticmethod
    def version_sort_key(version: str) -> tuple:
        normalized = str(version).strip().lstrip("vV").casefold()
        without_build = normalized.split("+", 1)[0]
        numeric, separator, prerelease = without_build.partition("-")
        numbers = [int(part) for part in numeric.split(".") if part.isdigit()]
        while len(numbers) < 4:
            numbers.append(0)
        tokens = tuple((1, int(token)) if token.isdigit() else (0, token) for token in re.findall(r"[a-z]+|\d+", prerelease))
        return *numbers[:4], 1 if not separator else 0, tokens

    @staticmethod
    def get_install_metadata(game_version: str, loader_version: str, force_refresh: bool = False) -> QuiltInstallMetadata:
        game_version = QuiltMetaClient._required_version(game_version, "Minecraft version")
        loader_version = QuiltMetaClient._required_version(loader_version, "Quilt Loader version")
        data = QuiltMetaClient._load_install_metadata(game_version, loader_version, force_refresh)
        if not isinstance(data, dict):
            raise RuntimeError("Quilt Meta returned invalid installation metadata.")

        loader = data.get("loader")
        mappings = QuiltMetaClient._mappings_component(data)
        launcher_meta = data.get("launcherMeta")
        if not isinstance(loader, dict) or not isinstance(launcher_meta, dict):
            raise RuntimeError("Quilt installation metadata is incomplete.")

        resolved_loader_version = str(loader.get("version", "")).strip()
        mappings_version = str(mappings.get("version", "")).strip() if isinstance(mappings, dict) else ""
        loader_maven = str(loader.get("maven", "")).strip()
        mappings_maven = str(mappings.get("maven", "")).strip() if isinstance(mappings, dict) else ""
        main_classes = launcher_meta.get("mainClass", {})
        main_class = str(main_classes.get("client", "")).strip() if isinstance(main_classes, dict) else ""

        if resolved_loader_version != loader_version:
            raise RuntimeError(f"Quilt Meta resolved Loader {resolved_loader_version or 'unknown'} instead of {loader_version}.")
        if not loader_maven or not main_class:
            raise RuntimeError("Quilt installation metadata is missing a required component.")
        if bool(mappings_version) != bool(mappings_maven):
            raise RuntimeError("Quilt installation metadata contains an incomplete mappings component.")

        libraries_data = launcher_meta.get("libraries", {})
        libraries: list[dict] = []
        if isinstance(libraries_data, dict):
            for group in ("common", "client"):
                values = libraries_data.get(group, [])
                if isinstance(values, list):
                    libraries.extend(item for item in values if isinstance(item, dict))

        mappings_component = None
        if mappings_version and mappings_maven:
            mappings_component = QuiltComponent(
                uid=QuiltMetaClient._component_uid(mappings_maven, "org.quiltmc.hashed"),
                version=mappings_version,
                maven=mappings_maven,
            )
        loader_uid = QuiltMetaClient._component_uid(loader_maven, "org.quiltmc.quilt-loader")
        return QuiltInstallMetadata(
            game=QuiltComponent(uid="net.minecraft", version=game_version),
            mappings=mappings_component,
            loader=QuiltComponent(uid=loader_uid, version=resolved_loader_version, maven=loader_maven),
            main_class=main_class,
            libraries=tuple(libraries),
        )

    @staticmethod
    def get_profile(game_version: str, loader_version: str, force_refresh: bool = False) -> dict:
        game_version = QuiltMetaClient._required_version(game_version, "Minecraft version")
        loader_version = QuiltMetaClient._required_version(loader_version, "Quilt Loader version")
        data = QuiltMetaClient._load_profile(game_version, loader_version, force_refresh)
        if not isinstance(data, dict) or not data.get("mainClass"):
            raise RuntimeError(f"Quilt profile is unavailable for Minecraft {game_version} and Loader {loader_version}.")
        return data

    @staticmethod
    def clear_cached_install(game_version: str, loader_version: str) -> None:
        for path in (Paths.quilt_install_metadata_json(game_version, loader_version), Paths.quilt_profile_json(game_version, loader_version)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _mappings_component(data: dict) -> object:
        for key in ("hashed", "intermediary", "mappings"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _component_uid(maven: str, fallback: str) -> str:
        parts = str(maven).split(":")
        return ".".join(parts[:2]) if len(parts) >= 2 else fallback

    @staticmethod
    def _load_catalog(game_version: str, force_refresh: bool) -> object:
        path = Paths.quilt_catalog_json(game_version)
        with QuiltMetaClient._get_cache_lock(path):
            cached = QuiltMetaClient._read_cache(path, QuiltMetaClient.CATALOG_CACHE_SCHEMA, gameVersion=game_version)
            if cached is not None and not force_refresh:
                try:
                    fetched_at = float(cached.get("fetchedAt", 0) or 0)
                except (TypeError, ValueError):
                    fetched_at = 0
                if time() - fetched_at <= QuiltMetaClient.CATALOG_TTL_SECONDS:
                    return cached.get("payload")
            encoded_game = quote(game_version, safe="")
            return QuiltMetaClient._refresh_with_fallback(path, QuiltMetaClient.CATALOG_CACHE_SCHEMA, {"gameVersion": game_version}, f"/versions/loader/{encoded_game}", cached)

    @staticmethod
    def _load_install_metadata(game_version: str, loader_version: str, force_refresh: bool) -> object:
        path = Paths.quilt_install_metadata_json(game_version, loader_version)
        with QuiltMetaClient._get_cache_lock(path):
            identity = {"gameVersion": game_version, "loaderVersion": loader_version}
            cached = QuiltMetaClient._read_cache(path, QuiltMetaClient.INSTALL_CACHE_SCHEMA, **identity)
            if cached is not None and not force_refresh:
                return cached.get("payload")
            encoded_game = quote(game_version, safe="")
            encoded_loader = quote(loader_version, safe="")
            return QuiltMetaClient._refresh_with_fallback(path, QuiltMetaClient.INSTALL_CACHE_SCHEMA, identity, f"/versions/loader/{encoded_game}/{encoded_loader}", cached)

    @staticmethod
    def _load_profile(game_version: str, loader_version: str, force_refresh: bool) -> object:
        path = Paths.quilt_profile_json(game_version, loader_version)
        with QuiltMetaClient._get_cache_lock(path):
            identity = {"gameVersion": game_version, "loaderVersion": loader_version}
            cached = QuiltMetaClient._read_cache(path, QuiltMetaClient.PROFILE_CACHE_SCHEMA, **identity)
            if cached is not None and not force_refresh:
                return cached.get("payload")
            encoded_game = quote(game_version, safe="")
            encoded_loader = quote(loader_version, safe="")
            return QuiltMetaClient._refresh_with_fallback(path, QuiltMetaClient.PROFILE_CACHE_SCHEMA, identity, f"/versions/loader/{encoded_game}/{encoded_loader}/profile/json", cached)

    @staticmethod
    def _get_cache_lock(path: Path) -> Lock:
        try:
            normalized = path.resolve(strict=False)
        except OSError:
            normalized = path.absolute()
        with QuiltMetaClient._cache_locks_guard:
            return QuiltMetaClient._cache_locks.setdefault(normalized, Lock())

    @staticmethod
    def _refresh_with_fallback(path: Path, schema: int, identity: dict[str, str], request_path: str, cached: dict | None) -> object:
        try:
            payload = QuiltMetaClient._get_json(request_path)
        except RuntimeError:
            if cached is not None:
                return cached.get("payload")
            raise
        QuiltMetaClient._write_cache(path, schema, identity, payload)
        return payload

    @staticmethod
    def _get_json(path: str) -> object:
        client = HttpDownloader.get_client()
        try:
            response = client.get(QuiltMetaClient.BASE_URL + path, timeout=20.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError("Unable to contact Quilt Meta and no cached metadata is available.") from error

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
        return data

    @staticmethod
    def _write_cache(path: Path, schema: int, identity: dict[str, str], payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"schemaVersion": schema, **identity, "fetchedAt": time(), "payload": payload}
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _required_version(value: str, label: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise RuntimeError(f"{label} is required.")
        return normalized
