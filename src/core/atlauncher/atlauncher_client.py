from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import PurePosixPath
import re
from typing import Iterable
from urllib.parse import quote, urljoin

import httpx

from src.config import ATLAUNCHER_USER_AGENT
from src.core.atlauncher.atlauncher_cache import ATLauncherApiCache, ATLauncherApiCacheLookup
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.atlauncher.cache import ATLauncherCacheInfo
from src.models.atlauncher.pack import ATLauncherPack, ATLauncherSearchResult
from src.models.atlauncher.version import ATLauncherConfigBundle, ATLauncherFile, ATLauncherVersion, ATLauncherVersionSummary


class ATLauncherClient:
    """ATLauncher metadata adapter with public V2, V1, and CDN fallbacks.

    The V2 provider API is still marked beta, so GraphQL details stay behind a
    small public contract while stable V1/CDN endpoints provide installation
    metadata when the browse schema is unavailable.
    """

    GRAPHQL_URL = "https://api.atlauncher.com/v2/graphql"
    V1_BASE_URL = "https://api.atlauncher.com/v1/"
    CDN_BASE_URL = "https://download.nodecdn.net/containers/atl/"
    WEBSITE_BASE_URL = "https://atlauncher.com/pack/"
    SEARCH_TTL_SECONDS = 5 * 60
    PROJECT_TTL_SECONDS = 15 * 60
    VERSION_TTL_SECONDS = 30 * 60
    REQUEST_TIMEOUT_SECONDS = 25.0
    MAX_PAGE_SIZE = 50
    MAX_SEARCH_WINDOW = 250

    _PACK_FIELDS = """
        id
        position
        name
        safeName
        latestVersion {
            id
            version
            minecraftVersion
            changelog
            isRecommended
            canUpdate
            createdAt
            updatedAt
            publishedAt
        }
    """

    @staticmethod
    def api_cache_status() -> ATLauncherCacheInfo:
        return ATLauncherApiCache.status()

    @staticmethod
    def clear_api_cache() -> None:
        ATLauncherApiCache.clear()

    @staticmethod
    def cache_status() -> ATLauncherCacheInfo:
        """Compatibility alias for the pre-v1.3 API-cache name."""
        return ATLauncherClient.api_cache_status()

    @staticmethod
    def clear_cache() -> None:
        """Compatibility alias; clears provider API metadata only."""
        ATLauncherClient.clear_api_cache()

    @staticmethod
    def search_projects(query: str = "", index: int = 0, page_size: int = 25, sort: str = "popularity", force_refresh: bool = False) -> ATLauncherSearchResult:
        normalized_query = " ".join(str(query).split())
        normalized_index = max(0, int(index))
        normalized_page_size = min(max(1, int(page_size)), ATLauncherClient.MAX_PAGE_SIZE)
        fetch_count = min(ATLauncherClient.MAX_SEARCH_WINDOW, normalized_index + normalized_page_size + 1)
        variables = {"first": fetch_count, "query": normalized_query}
        if normalized_query:
            queries = (
                f"""query SearchPacks($first: Int!, $query: String!) {{
                    searchPacks(first: $first, query: $query, field: NAME) {{ {ATLauncherClient._PACK_FIELDS} }}
                }}""",
            )
            field = "searchPacks"
        else:
            queries = (
                f"""query Packs($first: Int!) {{
                    packs(first: $first) {{ {ATLauncherClient._PACK_FIELDS} }}
                }}""",
            )
            field = "packs"
        try:
            lookup = ATLauncherClient._request_graphql(
                queries,
                variables,
                ttl=ATLauncherClient.SEARCH_TTL_SECONDS,
                force_refresh=force_refresh,
                allow_stale_on_error=True,
                namespace="search" if normalized_query else "packs",
            )
            raw = ATLauncherClient._data_list(lookup.payload, field)
        except RuntimeError:
            lookup, raw = ATLauncherClient._search_v1(normalized_query, force_refresh)
        parsed = [ATLauncherClient._parse_pack(item) for item in raw if isinstance(item, dict)]
        parsed = [item for item in parsed if item.safe_name and item.name]
        parsed = ATLauncherClient._sort_projects(parsed, sort)
        page = tuple(parsed[normalized_index : normalized_index + normalized_page_size])
        has_more = len(parsed) > normalized_index + normalized_page_size
        known_total = len(parsed) if not has_more else normalized_index + len(page) + 1
        return ATLauncherSearchResult(
            projects=page,
            total_count=known_total,
            index=normalized_index,
            page_size=normalized_page_size,
            has_more=has_more,
            cache_info=lookup.cache_info,
        )

    @staticmethod
    def get_project(safe_name: str, force_refresh: bool = False) -> ATLauncherPack:
        token = ATLauncherClient._safe_name(safe_name)
        url = f"{ATLauncherClient.V1_BASE_URL}pack/{quote(token, safe='')}"
        try:
            lookup = ATLauncherClient._request_json(
                url,
                ttl=ATLauncherClient.PROJECT_TTL_SECONDS,
                force_refresh=force_refresh,
                allow_stale_on_error=True,
                namespace="project-v1",
            )
            payload = lookup.payload
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                payload = payload["data"]
            if not isinstance(payload, dict):
                raise RuntimeError(f"ATLauncher pack '{token}' is unavailable.")
            project = ATLauncherClient._parse_pack(payload)
        except RuntimeError:
            project = ATLauncherClient._get_project_v2(token, force_refresh)
        if not project.safe_name:
            raise RuntimeError(f"ATLauncher pack '{token}' returned invalid metadata.")
        return project

    @staticmethod
    def get_project_details(safe_name: str, force_refresh: bool = False) -> ATLauncherPack:
        return ATLauncherClient.get_project(safe_name, force_refresh=force_refresh)

    @staticmethod
    def list_versions(safe_name: str, release_types: Iterable[str] | None = None, force_refresh: bool = False) -> tuple[ATLauncherVersionSummary, ...]:
        project = ATLauncherClient.get_project(safe_name, force_refresh=force_refresh)
        allowed = ATLauncherClient._normalized_release_types(release_types)
        versions = [version for version in project.versions if version.release_type in allowed]
        versions.sort(key=lambda item: (item.published_at, item.updated_at, item.version_id, item.version), reverse=True)
        return tuple(versions)

    @staticmethod
    def get_version(safe_name: str, version: str, force_refresh: bool = False) -> ATLauncherVersion:
        token = ATLauncherClient._safe_name(safe_name)
        version_name = str(version).strip()
        if not version_name or len(version_name) > 160 or any(character in version_name for character in "\\/\x00\r\n"):
            raise RuntimeError("Invalid ATLauncher pack version identifier.")
        manifest_url = f"{ATLauncherClient.CDN_BASE_URL}packs/{quote(token, safe='')}/versions/{quote(version_name, safe='')}/Configs.json"
        try:
            lookup = ATLauncherClient._request_json(
                manifest_url,
                ttl=ATLauncherClient.VERSION_TTL_SECONDS,
                force_refresh=force_refresh,
                allow_stale_on_error=True,
                namespace="version-manifest",
            )
            manifest = lookup.payload
            if isinstance(manifest, dict) and isinstance(manifest.get("data"), dict):
                manifest = manifest["data"]
            if not isinstance(manifest, dict):
                raise RuntimeError("ATLauncher returned an invalid installation manifest.")
        except RuntimeError:
            legacy_url = f"{ATLauncherClient.V1_BASE_URL}pack/{quote(token, safe='')}/{quote(version_name, safe='')}"
            lookup = ATLauncherClient._request_json(
                legacy_url,
                ttl=ATLauncherClient.VERSION_TTL_SECONDS,
                force_refresh=force_refresh,
                allow_stale_on_error=True,
                namespace="version-v1",
            )
            manifest = lookup.payload
            if isinstance(manifest, dict) and isinstance(manifest.get("data"), dict):
                manifest = manifest["data"]
            if not isinstance(manifest, dict):
                raise RuntimeError(f"ATLauncher pack version '{version_name}' is unavailable.")
        summary = ATLauncherClient._find_version_summary(token, version_name)
        metadata = {
            "id": summary.version_id if summary is not None else version_name,
            "version": version_name,
            "minecraftVersion": summary.minecraft_version if summary is not None else manifest.get("minecraft"),
            "changelog": summary.changelog if summary is not None else manifest.get("changelog"),
            "isRecommended": summary.recommended if summary is not None else bool(manifest.get("recommended", False)),
            "isDevelopment": summary.development if summary is not None else bool(manifest.get("development", False)),
            "publishedAt": summary.published_at if summary is not None else manifest.get("published"),
            "rawJson": manifest,
        }
        return ATLauncherClient._parse_version(token, metadata)

    @staticmethod
    def normalize_loader(value: object) -> str:
        name = str(value or "").strip().casefold().replace(" ", "").replace("_", "").replace("-", "")
        aliases = {
            "": ModLoaderManager.VANILLA,
            "vanilla": ModLoaderManager.VANILLA,
            "minecraft": ModLoaderManager.VANILLA,
            "forge": ModLoaderManager.FORGE,
            "minecraftforge": ModLoaderManager.FORGE,
            "neoforge": ModLoaderManager.NEOFORGE,
            "fabric": ModLoaderManager.FABRIC,
            "fabricloader": ModLoaderManager.FABRIC,
            "quilt": ModLoaderManager.QUILT,
            "quiltloader": ModLoaderManager.QUILT,
        }
        return aliases.get(name, name)

    @staticmethod
    def _request_graphql(queries: tuple[str, ...], variables: dict[str, object], ttl: int, force_refresh: bool, allow_stale_on_error: bool, namespace: str) -> ATLauncherApiCacheLookup:
        cache_key = ATLauncherApiCache.make_key(namespace, "graphql", {"variables": variables, "queries": queries})
        if not force_refresh:
            cached = ATLauncherApiCache.get(cache_key, ttl)
            if cached is not None:
                return cached
        errors: list[str] = []
        for query in queries:
            try:
                response = HttpDownloader.get_client().post(
                    ATLauncherClient.GRAPHQL_URL,
                    headers=ATLauncherClient._headers(),
                    json={"query": query, "variables": variables},
                    timeout=ATLauncherClient.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("ATLauncher returned a non-object GraphQL response.")
                graphql_errors = payload.get("errors")
                if isinstance(graphql_errors, list) and graphql_errors:
                    detail = "; ".join(
                        str(item.get("message") if isinstance(item, dict) else item).strip()
                        for item in graphql_errors
                        if str(item.get("message") if isinstance(item, dict) else item).strip()
                    )
                    raise RuntimeError(detail or "ATLauncher GraphQL request failed.")
                if not isinstance(payload.get("data"), dict):
                    raise RuntimeError("ATLauncher GraphQL response did not contain data.")
                return ATLauncherApiCache.put(cache_key, namespace, payload, ttl)
            except (httpx.HTTPError, ValueError, RuntimeError) as error:
                errors.append(str(error) or type(error).__name__)
        return ATLauncherClient._stale_or_error(cache_key, ttl, namespace, errors, allow_stale_on_error)

    @staticmethod
    def _request_json(url: str, ttl: int, force_refresh: bool, allow_stale_on_error: bool, namespace: str) -> ATLauncherApiCacheLookup:
        cache_key = ATLauncherApiCache.make_key(namespace, url)
        if not force_refresh:
            cached = ATLauncherApiCache.get(cache_key, ttl)
            if cached is not None:
                return cached
        errors: list[str] = []
        try:
            response = HttpDownloader.get_client().get(url, headers=ATLauncherClient._headers(), timeout=ATLauncherClient.REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, (dict, list)):
                raise RuntimeError("ATLauncher returned an unsupported JSON response.")
            return ATLauncherApiCache.put(cache_key, namespace, payload, ttl)
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            errors.append(str(error) or type(error).__name__)
        return ATLauncherClient._stale_or_error(cache_key, ttl, namespace, errors, allow_stale_on_error)

    @staticmethod
    def _stale_or_error(cache_key: str, ttl: int, namespace: str, errors: list[str], allow_stale_on_error: bool) -> ATLauncherApiCacheLookup:
        detail = "; ".join(dict.fromkeys(item for item in errors if item)) or "No ATLauncher endpoint responded."
        ATLauncherApiCache.record_failure(detail)
        if allow_stale_on_error:
            stale = ATLauncherApiCache.get(cache_key, ttl, allow_stale=True)
            if stale is not None:
                return stale
        raise RuntimeError(f"Could not contact the ATLauncher service ({namespace}): {detail}")

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"User-Agent": ATLAUNCHER_USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"}

    @staticmethod
    def _search_v1(query: str, force_refresh: bool) -> tuple[ATLauncherApiCacheLookup, list]:
        urls = (
            f"{ATLauncherClient.V1_BASE_URL}packs/full/public",
            f"{ATLauncherClient.CDN_BASE_URL}launcher/json/packsnew.json",
        )
        errors: list[str] = []
        for url in urls:
            try:
                lookup = ATLauncherClient._request_json(url, ATLauncherClient.SEARCH_TTL_SECONDS, force_refresh, True, "packs-v1")
                payload = lookup.payload
                if isinstance(payload, dict):
                    for key in ("packs", "data", "results"):
                        if isinstance(payload.get(key), list):
                            payload = payload[key]
                            break
                raw = payload if isinstance(payload, list) else []
                if query:
                    needle = query.casefold()
                    raw = [item for item in raw if isinstance(item, dict) and needle in ATLauncherClient._text(item.get("name")).casefold()]
                return lookup, raw
            except RuntimeError as error:
                errors.append(str(error))
        raise RuntimeError("; ".join(errors) or "Could not list ATLauncher packs.")

    @staticmethod
    def _get_project_v2(token: str, force_refresh: bool) -> ATLauncherPack:
        variables = {"safeName": token}
        query = f"""query Pack($safeName: String!) {{
            pack(safeName: $safeName) {{ {ATLauncherClient._PACK_FIELDS} }}
        }}"""
        lookup = ATLauncherClient._request_graphql((query,), variables, ATLauncherClient.PROJECT_TTL_SECONDS, force_refresh, True, "project-v2")
        payload = ATLauncherClient._data_value(lookup.payload, "pack")
        if not isinstance(payload, dict):
            raise RuntimeError(f"ATLauncher pack '{token}' is unavailable.")
        return ATLauncherClient._parse_pack(payload)

    @staticmethod
    def _find_version_summary(safe_name: str, version_name: str) -> ATLauncherVersionSummary | None:
        try:
            project = ATLauncherClient.get_project(safe_name)
        except RuntimeError:
            return None
        return next((item for item in project.versions if item.version == version_name), None)

    @staticmethod
    def _parse_pack(data: dict) -> ATLauncherPack:
        safe_name = ATLauncherClient._text(data.get("safeName"))
        name = ATLauncherClient._text(data.get("name")) or safe_name
        if not safe_name and name:
            safe_name = re.sub(r"[^A-Za-z0-9]", "", name)
        description = ATLauncherClient._text(data.get("description"))
        raw_versions = data.get("versions") if isinstance(data.get("versions"), list) else []
        latest = data.get("latestVersion") if isinstance(data.get("latestVersion"), dict) else None
        versions = [ATLauncherClient._parse_version_summary(item) for item in raw_versions if isinstance(item, dict)]
        if latest is not None:
            latest_summary = ATLauncherClient._parse_version_summary(latest)
            if latest_summary.version and all(item.version != latest_summary.version for item in versions):
                versions.insert(0, latest_summary)
        versions = [item for item in versions if item.version]
        versions.sort(key=lambda item: (item.published_at, item.updated_at, item.version_id, item.version), reverse=True)
        icon_token = re.sub(r"[^A-Za-z0-9]", "", name).casefold() + ".png" if name else ""
        icon_url = f"{ATLauncherClient.CDN_BASE_URL}launcher/images/{quote(icon_token, safe='')}" if icon_token else ""
        website = ATLauncherClient._text(data.get("websiteURL") or data.get("websiteUrl"))
        if not website and safe_name:
            website = ATLauncherClient.WEBSITE_BASE_URL + quote(safe_name, safe="")
        latest_updated = ATLauncherClient._iso(latest.get("updatedAt") or latest.get("updated")) if latest is not None else ""
        latest_created = ATLauncherClient._iso(latest.get("createdAt") or latest.get("created") or latest.get("publishedAt") or latest.get("published")) if latest is not None else ""
        return ATLauncherPack(
            pack_id=ATLauncherClient._text(data.get("id")),
            safe_name=safe_name,
            name=name,
            synopsis=ATLauncherClient._first_sentence(description),
            description=description,
            icon_url=icon_url,
            position=ATLauncherClient._int(data.get("position")),
            updated_at=ATLauncherClient._iso(data.get("updatedAt") or data.get("updated")) or latest_updated,
            created_at=ATLauncherClient._iso(data.get("createdAt") or data.get("created")) or latest_created,
            website_url=website,
            support_url=ATLauncherClient._text(data.get("supportURL") or data.get("supportUrl")),
            pack_type=ATLauncherClient._text(data.get("type")),
            versions=tuple(versions),
        )

    @staticmethod
    def _parse_version_summary(data: dict) -> ATLauncherVersionSummary:
        version_name = ATLauncherClient._text(data.get("version") or data.get("name"))
        return ATLauncherVersionSummary(
            version_id=ATLauncherClient._text(data.get("id")) or version_name,
            version=version_name,
            minecraft_version=ATLauncherClient._text(data.get("minecraftVersion") or data.get("minecraft")),
            changelog=ATLauncherClient._text(data.get("changelog")),
            recommended=bool(data.get("isRecommended", data.get("recommended", False))),
            development=bool(data.get("isDevelopment", data.get("development", False))),
            created_at=ATLauncherClient._iso(data.get("createdAt") or data.get("created")),
            updated_at=ATLauncherClient._iso(data.get("updatedAt") or data.get("updated")),
            published_at=ATLauncherClient._iso(data.get("publishedAt") or data.get("published")),
        )


    @staticmethod
    def _parse_version(safe_name: str, data: dict) -> ATLauncherVersion:
        raw = data.get("rawJson")
        if isinstance(raw, str):
            try:
                manifest = json.loads(raw)
            except json.JSONDecodeError as error:
                raise RuntimeError("ATLauncher returned invalid raw pack metadata.") from error
        elif isinstance(raw, dict):
            manifest = raw
        else:
            manifest = {}
        if not isinstance(manifest, dict):
            raise RuntimeError("ATLauncher pack metadata is not an object.")
        minecraft = ATLauncherClient._text(manifest.get("minecraft") or data.get("minecraftVersion"))
        loader_name, loader_version = ATLauncherClient._loader(manifest)
        files: list[ATLauncherFile] = []
        for collection, library in ((manifest.get("libraries"), True), (manifest.get("mods"), False)):
            if not isinstance(collection, list):
                continue
            for index, item in enumerate(collection):
                if not isinstance(item, dict) or ATLauncherClient._is_loader_file(item, loader_name):
                    continue
                parsed = ATLauncherClient._parse_file(safe_name, data, item, index, library)
                if parsed is not None:
                    files.append(parsed)
        config_bundle = None
        configs = manifest.get("configs") if isinstance(manifest.get("configs"), dict) else {}
        no_configs = bool(manifest.get("noConfigs", False))
        config_sha1 = ATLauncherClient._text(configs.get("sha1") or configs.get("hash"))
        config_size = ATLauncherClient._int(configs.get("size") or configs.get("filesize"))
        version_name = ATLauncherClient._text(data.get("version") or manifest.get("version"))
        if not no_configs and version_name and (config_sha1 or config_size > 0):
            url = f"{ATLauncherClient.CDN_BASE_URL}packs/{quote(safe_name, safe='')}/versions/{quote(version_name, safe='')}/Configs.zip"
            config_bundle = ATLauncherConfigBundle(url=url, sha1=config_sha1, size=config_size)
        unsupported = ATLauncherClient._unsupported_actions(manifest, files)
        memory = manifest.get("memory") if isinstance(manifest.get("memory"), dict) else {}
        minimum_memory = ATLauncherClient._memory_mb(memory.get("minimum") or manifest.get("minimumMemory"))
        recommended_memory = ATLauncherClient._memory_mb(memory.get("recommended") or manifest.get("recommendedMemory"))
        warnings: list[str] = []
        if any(file.download_type == "browser" for file in files):
            warnings.append("Some pack files require a browser-assisted download and cannot be installed automatically yet.")
        return ATLauncherVersion(
            pack_id=ATLauncherClient._text(data.get("packId")),
            safe_name=safe_name,
            version_id=ATLauncherClient._text(data.get("id")) or version_name,
            version=version_name,
            minecraft_version=minecraft,
            changelog=ATLauncherClient._text(data.get("changelog")),
            recommended=bool(data.get("isRecommended", False)),
            development=bool(data.get("isDevelopment", False)),
            loader=loader_name,
            loader_version=loader_version,
            files=tuple(files),
            config_bundle=config_bundle,
            minimum_memory_mb=minimum_memory,
            recommended_memory_mb=recommended_memory,
            java_version=ATLauncherClient._text(manifest.get("java") or manifest.get("javaVersion")),
            warnings=tuple(warnings),
            unsupported_actions=tuple(unsupported),
            published_at=ATLauncherClient._iso(data.get("publishedAt")),
            raw_manifest=manifest,
        )

    @staticmethod
    def _parse_file(safe_name: str, version_data: dict, item: dict, index: int, library: bool) -> ATLauncherFile | None:
        name = ATLauncherClient._text(item.get("name"))
        filename = ATLauncherClient._text(item.get("file"))
        if not filename:
            return None
        raw_type = ATLauncherClient._text(item.get("type") or ("library" if library else "mods")).casefold()
        path = ATLauncherClient._destination(raw_type, filename, item, ATLauncherClient._text(version_data.get("minecraftVersion")))
        raw_download = ATLauncherClient._text(item.get("download") or item.get("downloadType") or "direct").casefold()
        source = ATLauncherClient._text(item.get("url") or item.get("server"))
        urls = ATLauncherClient._urls(safe_name, ATLauncherClient._text(version_data.get("version")), source, raw_download)
        dependencies = item.get("depends") or item.get("dependencies") or ()
        if isinstance(dependencies, str):
            dependency_values = tuple(value.strip() for value in dependencies.split(",") if value.strip())
        elif isinstance(dependencies, list):
            dependency_values = tuple(ATLauncherClient._text(value) for value in dependencies if ATLauncherClient._text(value))
        else:
            dependency_values = ()
        optional = bool(item.get("optional", False))
        selected = bool(item.get("selected", item.get("default", False)))
        recommended = bool(item.get("recommended", selected))
        client_value = item.get("client")
        return ATLauncherFile(
            file_id=ATLauncherClient._text(item.get("id")) or f"{index}:{filename}",
            name=name or PurePosixPath(filename.replace("\\", "/")).name,
            path=path,
            urls=urls,
            sha1=ATLauncherClient._text(item.get("sha1")).casefold(),
            md5=ATLauncherClient._text(item.get("md5")).casefold(),
            size=max(0, ATLauncherClient._int(item.get("size") or item.get("filesize"))),
            download_type=raw_download or "direct",
            optional=optional,
            selected=selected,
            recommended=recommended,
            client_only=client_value is True,
            server_only=client_value is False,
            library=library or bool(item.get("library", False)) or raw_type in {"library", "dependency", "depandency"},
            dependencies=dependency_values,
            extract_to=ATLauncherClient._text(item.get("extractTo")),
            extract_folder=ATLauncherClient._text(item.get("extractFolder")).replace("%s%", "/"),
            decomp_type=ATLauncherClient._text(item.get("decompType")),
            decomp_file=ATLauncherClient._text(item.get("decompFile")),
            force=bool(item.get("force", False)),
        )

    @staticmethod
    def _loader(manifest: dict) -> tuple[str, str]:
        loader = manifest.get("loader") if isinstance(manifest.get("loader"), dict) else {}
        name = ATLauncherClient.normalize_loader(loader.get("type"))
        metadata = loader.get("metadata") if isinstance(loader.get("metadata"), dict) else {}
        version = ATLauncherClient._text(metadata.get("loader") or metadata.get("rawVersion") or metadata.get("version") or loader.get("version"))
        if not loader:
            mods = manifest.get("mods") if isinstance(manifest.get("mods"), list) else ()
            for item in mods:
                if not isinstance(item, dict):
                    continue
                item_name = ATLauncherClient._text(item.get("name")).casefold()
                item_type = ATLauncherClient._text(item.get("type")).casefold()
                if "neoforge" in item_name:
                    return ModLoaderManager.NEOFORGE, ATLauncherClient._text(item.get("version")) or ModLoaderManager.AUTO
                if item_type == "forge" or item_name == "minecraft forge":
                    return ModLoaderManager.FORGE, ATLauncherClient._text(item.get("version")) or ModLoaderManager.AUTO
        if name == ModLoaderManager.VANILLA:
            return name, "-1"
        if (metadata.get("recommended") or metadata.get("latest") or loader.get("choose")) and not version:
            version = ModLoaderManager.AUTO
        return name, version or ModLoaderManager.AUTO

    @staticmethod
    def _is_loader_file(item: dict, loader_name: str) -> bool:
        name = ATLauncherClient._text(item.get("name")).casefold()
        raw_type = ATLauncherClient._text(item.get("type")).casefold()
        if loader_name == ModLoaderManager.FORGE and (raw_type == "forge" or name == "minecraft forge"):
            return True
        if loader_name == ModLoaderManager.NEOFORGE and "neoforge" in name:
            return True
        return False

    @staticmethod
    def _destination(raw_type: str, filename: str, item: dict, minecraft_version: str) -> str:
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        mapping = {
            "mods": "mods",
            "mod": "mods",
            "library": ".mcw/atlauncher/libraries",
            "coremods": "coremods",
            "flan": "Flan",
            "ic2lib": "mods/ic2",
            "denlib": "mods/denlib",
            "plugins": "plugins",
            "texturepack": "texturepacks",
            "resourcepack": "resourcepacks",
            "shaderpack": "shaderpacks",
        }
        if raw_type in {"dependency", "depandency"}:
            directory = f"mods/{minecraft_version}" if minecraft_version else "mods"
        elif raw_type in {"root", "jar", "forge", "mcpc"}:
            directory = ".mcw/atlauncher/legacy"
        elif raw_type in {"extract", "texturepackextract", "resourcepackextract", "decomp"}:
            directory = ".mcw/atlauncher/downloads"
        else:
            directory = mapping.get(raw_type, "mods")
        prefix = ATLauncherClient._text(item.get("filePrefix") or item.get("path")).replace("\\", "/").strip("/")
        if prefix:
            directory = f"{directory}/{prefix}"
        return f"{directory}/{safe_filename}" if directory else safe_filename

    @staticmethod
    def _urls(safe_name: str, version: str, source: str, download_type: str) -> tuple[str, ...]:
        if download_type == "browser":
            return (source,) if source.startswith(("http://", "https://")) else ()
        if download_type == "direct":
            return (source,) if source.startswith(("http://", "https://")) else ()
        if download_type == "server":
            if not source:
                return ()
            return (urljoin(ATLauncherClient.CDN_BASE_URL, source.lstrip("/")),)
        if source.startswith(("http://", "https://")):
            return (source,)
        if not source:
            return ()
        relative = source.lstrip("/")
        candidates = [urljoin(ATLauncherClient.CDN_BASE_URL, relative)]
        if safe_name and version:
            candidates.append(f"{ATLauncherClient.CDN_BASE_URL}packs/{quote(safe_name, safe='')}/versions/{quote(version, safe='')}/{relative}")
        return tuple(dict.fromkeys(candidates))

    @staticmethod
    def _unsupported_actions(manifest: dict, files: list[ATLauncherFile]) -> list[str]:
        values: list[str] = []
        for key in ("actions", "installActions", "postInstallActions", "delete", "keep"):
            raw = manifest.get(key)
            if isinstance(raw, list) and raw:
                values.append(key)
            elif isinstance(raw, dict) and raw:
                values.append(key)
        if isinstance(manifest.get("libraries"), list) and manifest["libraries"]:
            values.append("custom-libraries")
        main_class = manifest.get("mainClass")
        extra_arguments = manifest.get("extraArguments")
        if (isinstance(main_class, dict) and main_class) or (isinstance(main_class, str) and main_class.strip()):
            values.append("custom-main-class")
        if (isinstance(extra_arguments, dict) and extra_arguments) or (isinstance(extra_arguments, str) and extra_arguments.strip()):
            values.append("custom-extra-arguments")
        for file in files:
            if file.extract_to or file.extract_folder:
                values.append(f"extract:{file.name}")
            if file.decomp_type or file.decomp_file:
                values.append(f"decomp:{file.name}")
            if file.path.startswith(".mcw/atlauncher/legacy/"):
                values.append(f"legacy:{file.name}")
        return list(dict.fromkeys(values))

    @staticmethod
    def _sort_projects(projects: list[ATLauncherPack], value: str) -> list[ATLauncherPack]:
        normalized = str(value or "popularity").strip().casefold()
        if normalized == "name":
            return sorted(projects, key=lambda item: item.name.casefold())
        if normalized == "updated":
            return sorted(projects, key=lambda item: (item.updated_at, item.position), reverse=True)
        if normalized == "newest":
            return sorted(projects, key=lambda item: (item.created_at, item.position), reverse=True)
        return sorted(projects, key=lambda item: (item.position <= 0, item.position, item.name.casefold()))


    @staticmethod
    def _normalized_release_types(values: Iterable[str] | None) -> frozenset[str]:
        if values is None:
            return frozenset({"release", "beta", "alpha"})
        normalized = {str(value).strip().casefold() for value in values if str(value).strip()}
        return frozenset(normalized or {"release"})

    @staticmethod
    def _data_value(payload: object, field: str) -> object:
        data = payload.get("data") if isinstance(payload, dict) else None
        return data.get(field) if isinstance(data, dict) else None

    @staticmethod
    def _data_list(payload: object, field: str) -> list:
        value = ATLauncherClient._data_value(payload, field)
        return value if isinstance(value, list) else []

    @staticmethod
    def _safe_name(value: object) -> str:
        token = ATLauncherClient._text(value)
        if not token or len(token) > 120 or any(character in token for character in "\\/\x00\r\n"):
            raise RuntimeError("Invalid ATLauncher pack identifier.")
        return token

    @staticmethod
    def _first_sentence(value: str) -> str:
        normalized = " ".join(str(value).split())
        if not normalized:
            return ""
        for marker in (". ", "! ", "? "):
            if marker in normalized:
                return normalized.split(marker, 1)[0] + marker.strip()
        return normalized[:240]

    @staticmethod
    def _memory_mb(value: object) -> int:
        if isinstance(value, str):
            raw = value.strip().casefold()
            multiplier = 1024 if raw.endswith("g") else 1
            raw = raw.rstrip("mgb ")
            try:
                return max(0, int(float(raw) * multiplier))
            except ValueError:
                return 0
        return max(0, ATLauncherClient._int(value))

    @staticmethod
    def _iso(value: object) -> str:
        if isinstance(value, (int, float)) and value > 0:
            try:
                return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return ""
        text = ATLauncherClient._text(value)
        if text.isdigit():
            try:
                return datetime.fromtimestamp(float(text), timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return text
        return text

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    @staticmethod
    def _int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
