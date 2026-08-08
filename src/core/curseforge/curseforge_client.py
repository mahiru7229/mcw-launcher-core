from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock
from urllib.parse import quote, urlparse
import json
import re

import httpx

from src.config import CURSEFORGE_USER_AGENT, VERSION_ID
from src.core.config.curseforge_config_manager import CurseForgeConfigManager
from src.core.curseforge.curseforge_cache import CacheLookup, CurseForgeApiCache
from src.core.mod.provider_game_version_policy import provider_game_version_rank
from src.core.network.httpx_downloader import HttpDownloader
from src.models.curseforge.cache import CurseForgeCacheInfo, CurseForgeFileListResult
from src.models.curseforge.file import CurseForgeDependency, CurseForgeFile
from src.models.curseforge.project import CurseForgeProject, CurseForgeSearchResult


@dataclass(slots=True)
class _InFlightRequest:
    event: Event
    result: CacheLookup | None = None
    error: Exception | None = None


class CurseForgeClient:
    MINECRAFT_GAME_ID = 432

    CLASS_MODS = 6
    CLASS_RESOURCE_PACKS = 12
    CLASS_MODPACKS = 4471
    CLASS_SHADERS = 6552
    CLASS_IDS = {"mod": CLASS_MODS, "modpack": CLASS_MODPACKS, "resourcepack": CLASS_RESOURCE_PACKS, "shader": CLASS_SHADERS}
    SEARCH_TTL_SECONDS = 2 * 60
    FILES_TTL_SECONDS = 5 * 60
    PROJECT_TTL_SECONDS = 10 * 60
    FILE_TTL_SECONDS = 30 * 60
    BATCH_TTL_SECONDS = 30 * 60
    REQUEST_TIMEOUT_SECONDS = 15.0
    FAILOVER_STATUS_CODES = frozenset({404, 408, 425, 429,*range(500, 600),})
    PERMANENT_GATEWAY_CODES = frozenset({
        # Legacy gateway codes kept for compatibility with older deployments.
        "CURSEFORGE_CREDENTIALS_UNAVAILABLE",
        "FILE_UNAVAILABLE",
        "THIRD_PARTY_DISTRIBUTION_DISABLED",
        # Gateway v0.1.1 structured error codes.
        "MANUAL_DOWNLOAD_REQUIRED",
        "GATEWAY_CREDENTIALS_REJECTED",
        "UPSTREAM_FORBIDDEN",
        "UPSTREAM_REJECTED_REQUEST",
    })

    _inflight: dict[str, _InFlightRequest] = {}
    _inflight_guard = Lock()

    @staticmethod
    def is_available() -> bool:
        return CurseForgeConfigManager.is_configured()

    @staticmethod
    def gateway_urls() -> tuple[str, ...]:
        try:
            urls = CurseForgeConfigManager.gateway_urls()
        except (RuntimeError, ValueError) as error:
            raise RuntimeError(str(error)) from error
        if not urls:
            raise RuntimeError("No CurseForge gateway is configured. Add at least one protected gateway link in Launcher Settings.")
        return urls

    @staticmethod
    def gateway_url() -> str:
        return CurseForgeClient.gateway_urls()[0]

    @staticmethod
    def api_cache_status() -> CurseForgeCacheInfo:
        return CurseForgeApiCache.status()

    @staticmethod
    def clear_api_cache() -> None:
        CurseForgeApiCache.clear()

    @staticmethod
    def cache_status() -> CurseForgeCacheInfo:
        """Compatibility alias for the pre-v1.3 API-cache name."""
        return CurseForgeClient.api_cache_status()

    @staticmethod
    def clear_cache() -> None:
        """Compatibility alias; clears provider API metadata only."""
        CurseForgeClient.clear_api_cache()

    @staticmethod
    def manual_refresh_remaining_seconds() -> int:
        return CurseForgeApiCache.manual_refresh_remaining_seconds()

    @staticmethod
    def search_projects(project_type: str, query: str = "", game_version: str = "", loader: str = "forge", index: int = 0, page_size: int = 25, sort: str = "popularity", force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeSearchResult:
        kind = str(project_type).strip().lower()
        if kind not in CurseForgeClient.CLASS_IDS:
            raise ValueError("Unsupported CurseForge project type.")
        normalized_query = " ".join(str(query).strip().split())
        if not normalized_query:
            return CurseForgeSearchResult(
                projects=(),
                total_count=0,
                index=0,
                page_size=min(max(1, int(page_size)), 50),
                cache_info=CurseForgeApiCache.status(),
            )
        normalized_loader = CurseForgeClient.normalize_loader(loader) if kind in {"mod", "modpack"} else ""
        class_id = CurseForgeClient.CLASS_IDS[kind]
        sort_field = {"popularity": 2, "updated": 3, "newest": 11, "downloads": 6}.get(str(sort).lower(), 2)
        params: dict[str, object] = {
            "query": normalized_query,
            "classId": class_id,
            "sortField": sort_field,
            "sortOrder": "desc",
            "index": max(0, int(index)),
            "pageSize": min(max(1, int(page_size)), 50),
        }
        normalized_game_version = str(game_version).strip()
        # CurseForge's gameVersion field is advisory. Projects that declare a
        # nearby patch version can still work, so do not let the API hide them.
        lookup = CurseForgeClient._request_json(
            "GET",
            "/search",
            params=params,
            ttl=CurseForgeClient.SEARCH_TTL_SECONDS,
            force_refresh=force_refresh,
            manual_refresh=manual_refresh,
            allow_stale_on_error=True,
            namespace="search",
        )
        payload = lookup.payload
        data = payload.get("data", []) if isinstance(payload, dict) else []
        pagination = payload.get("pagination", {}) if isinstance(payload, dict) and isinstance(payload.get("pagination"), dict) else {}
        projects = tuple(CurseForgeClient._parse_project(item) for item in data if isinstance(item, dict))
        # Loader and game-version metadata are advisory. Keep every result and
        # rank likely matches first; the selected JAR is validated later.
        if normalized_loader or normalized_game_version:
            projects = tuple(sorted(
                enumerate(projects),
                key=lambda pair: (
                    CurseForgeClient._loader_rank(pair[1].loaders, normalized_loader),
                    provider_game_version_rank(normalized_game_version, pair[1].game_versions),
                    pair[0],
                ),
            ))
            projects = tuple(project for _, project in projects)
        return CurseForgeSearchResult(
            projects=projects,
            total_count=int(pagination.get("totalCount", len(projects)) or 0),
            index=int(pagination.get("index", index) or 0),
            page_size=int(pagination.get("pageSize", page_size) or page_size),
            cache_info=lookup.cache_info,
        )

    @staticmethod
    def get_project(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject:
        identifier = CurseForgeClient._positive_int(project_id, "Project ID")
        lookup = CurseForgeClient._request_json(
            "GET",
            "/mod",
            params={"modId": identifier},
            ttl=CurseForgeClient.PROJECT_TTL_SECONDS,
            force_refresh=force_refresh,
            allow_stale_on_error=True,
            namespace="project",
        )
        data = lookup.payload.get("data") if isinstance(lookup.payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"CurseForge project {identifier} is unavailable.")
        return CurseForgeClient._parse_project(data)

    @staticmethod
    def get_project_details(project_id: int | str, force_refresh: bool = False) -> CurseForgeProject:
        identifier = CurseForgeClient._positive_int(project_id, "Project ID")
        project = CurseForgeClient.get_project(identifier, force_refresh=force_refresh)
        try:
            lookup = CurseForgeClient._request_json(
                "GET",
                "/description",
                params={"modId": identifier},
                ttl=CurseForgeClient.PROJECT_TTL_SECONDS,
                force_refresh=force_refresh,
                allow_stale_on_error=True,
                namespace="project-description",
            )
        except RuntimeError:
            return project
        payload = lookup.payload.get("data") if isinstance(lookup.payload, dict) else ""
        description = str(payload or "").strip()
        return replace(project, description=description) if description else project

    @staticmethod
    def get_projects_batch(project_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeProject]:
        identifiers = CurseForgeClient._normalized_ids(project_ids, "Project ID")
        if not identifiers:
            return {}
        output: dict[int, CurseForgeProject] = {}
        for chunk in CurseForgeClient._chunks(identifiers, 50):
            lookup = CurseForgeClient._request_json(
                "POST",
                "/mods/batch",
                body={"modIds": list(chunk)},
                ttl=CurseForgeClient.BATCH_TTL_SECONDS,
                allow_stale_on_error=True,
                namespace="projects-batch",
            )
            data = lookup.payload.get("data", []) if isinstance(lookup.payload, dict) else []
            for item in data:
                if isinstance(item, dict):
                    project = CurseForgeClient._parse_project(item)
                    if project.project_id > 0:
                        output[project.project_id] = project
        return output

    @staticmethod
    def list_files_result(project_id: int | str, game_version: str = "", loader: str = "forge", release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False, manual_refresh: bool = False) -> CurseForgeFileListResult:
        identifier = CurseForgeClient._positive_int(project_id, "Project ID")
        normalized_loader = CurseForgeClient.normalize_loader(loader)
        params: dict[str, object] = {
            "modId": identifier,
            "pageSize": min(max(1, int(page_size)), 50),
            "index": 0,
        }
        # Do not send a strict loader filter. CurseForge metadata can label a
        # dual-loader JAR as only Fabric or only Forge. The selected loader is
        # therefore used for ranking and UI warnings; the downloaded JAR is the
        # final authority and is validated by ModManager before installation.
        # The same applies to gameVersion: nearby patch labels are useful for
        # ranking but must not remove files from the catalog.
        lookup = CurseForgeClient._request_json(
            "GET",
            "/files",
            params=params,
            ttl=CurseForgeClient.FILES_TTL_SECONDS,
            force_refresh=force_refresh,
            manual_refresh=manual_refresh,
            allow_stale_on_error=True,
            namespace="files",
        )
        data = lookup.payload.get("data", []) if isinstance(lookup.payload, dict) else []
        allowed = set(CurseForgeClient.normalize_release_types(release_types))
        normalized_game_version = str(game_version).strip()
        files = [CurseForgeClient._parse_file(item) for item in data if isinstance(item, dict)]
        files = [
            item for item in files
            if item.release_type in allowed
        ]
        files.sort(key=lambda item: item.file_date, reverse=True)
        files.sort(key=lambda item: (
            CurseForgeClient._loader_rank(item.loaders, normalized_loader),
            provider_game_version_rank(normalized_game_version, item.game_versions),
        ))
        return CurseForgeFileListResult(files=tuple(files), cache_info=lookup.cache_info)

    @staticmethod
    def list_files(project_id: int | str, game_version: str = "", loader: str = "forge", release_types: tuple[str, ...] | list[str] | set[str] | None = None, page_size: int = 50, force_refresh: bool = False) -> list[CurseForgeFile]:
        result = CurseForgeClient.list_files_result(
            project_id,
            game_version=game_version,
            loader=loader,
            release_types=release_types,
            page_size=page_size,
            force_refresh=force_refresh,
        )
        return list(result.files)

    @staticmethod
    def get_file(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> CurseForgeFile:
        project = CurseForgeClient._positive_int(project_id, "Project ID")
        file_identifier = CurseForgeClient._positive_int(file_id, "File ID")
        lookup = CurseForgeClient._request_json(
            "GET",
            "/file",
            params={"modId": project, "fileId": file_identifier},
            ttl=CurseForgeClient.FILE_TTL_SECONDS,
            force_refresh=force_refresh,
            allow_stale_on_error=True,
            namespace="file",
        )
        data = lookup.payload.get("data") if isinstance(lookup.payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError(f"CurseForge file {file_identifier} is unavailable.")
        return CurseForgeClient._parse_file(data)

    @staticmethod
    def get_files_batch(file_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, CurseForgeFile]:
        identifiers = CurseForgeClient._normalized_ids(file_ids, "File ID")
        if not identifiers:
            return {}
        output: dict[int, CurseForgeFile] = {}
        for chunk in CurseForgeClient._chunks(identifiers, 50):
            lookup = CurseForgeClient._request_json(
                "POST",
                "/files/batch",
                body={"fileIds": list(chunk)},
                ttl=CurseForgeClient.BATCH_TTL_SECONDS,
                allow_stale_on_error=True,
                namespace="files-batch",
            )
            data = lookup.payload.get("data", []) if isinstance(lookup.payload, dict) else []
            for item in data:
                if isinstance(item, dict):
                    file = CurseForgeClient._parse_file(item)
                    if file.file_id > 0:
                        output[file.file_id] = file
        return output

    @staticmethod
    def get_download_url(project_id: int | str, file_id: int | str, force_refresh: bool = False) -> str:
        project = CurseForgeClient._positive_int(project_id, "Project ID")
        file_identifier = CurseForgeClient._positive_int(file_id, "File ID")
        lookup = CurseForgeClient._request_json(
            "GET",
            "/download-url",
            params={"modId": project, "fileId": file_identifier},
            ttl=0,
            force_refresh=force_refresh,
            allow_stale_on_error=False,
            cache_response=False,
            namespace="download-url",
        )
        value = lookup.payload.get("data") if isinstance(lookup.payload, dict) else None
        return str(value or "").strip()

    @staticmethod
    def latest_compatible_file(project_id: int | str, game_version: str, loader: str = "forge", release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> CurseForgeFile:
        files = CurseForgeClient.list_files(project_id, game_version=game_version, loader=loader, release_types=release_types)
        normalized_game_version = str(game_version).strip()
        for file in files:
            loader_status = CurseForgeClient.loader_compatibility(file, loader)
            if loader_status not in {"compatible", "universal", "unknown"}:
                continue
            if normalized_game_version and file.game_versions and normalized_game_version not in file.game_versions:
                continue
            return file
        raise RuntimeError(f"No compatible {loader.title()} file for Minecraft {game_version} is available for CurseForge project {project_id}.")

    @staticmethod
    def normalize_loader(loader: str) -> str:
        normalized = str(loader).strip().casefold()
        if normalized in {"forge", "fabric", "quilt", "neoforge"}:
            return normalized
        return ""

    @staticmethod
    def loader_compatibility(file: CurseForgeFile, loader: str) -> str:
        return CurseForgeClient._loader_compatibility(file.loaders, loader)

    @staticmethod
    def is_permanent_error(error: BaseException) -> bool:
        code = str(getattr(error, "gateway_error_code", "") or "").strip().upper()
        if code in CurseForgeClient.PERMANENT_GATEWAY_CODES:
            return True
        status = int(getattr(error, "gateway_status", 0) or 0)
        if status in {400, 401, 403, 404}:
            return True
        message = str(error).casefold()
        return any(
            marker in message
            for marker in (
                "credentials are unavailable",
                "third-party distribution",
                "must be downloaded manually",
                "manual download required",
                "gateway credentials",
            )
        )

    @staticmethod
    def _loader_compatibility(loaders: tuple[str, ...] | list[str] | set[str], loader: str) -> str:
        normalized_loader = CurseForgeClient.normalize_loader(loader)
        normalized = {str(value).strip().casefold() for value in loaders if str(value).strip()}
        if normalized_loader in {"fabric", "forge"} and {"fabric", "forge"}.issubset(normalized):
            return "universal"
        if normalized_loader and normalized_loader in normalized:
            return "compatible"
        if normalized_loader == "quilt" and "fabric" in normalized:
            return "compatible"
        if not normalized:
            return "unknown"
        return "unverified"

    @staticmethod
    def _loader_rank(loaders: tuple[str, ...] | list[str] | set[str], loader: str) -> int:
        normalized_loader = CurseForgeClient.normalize_loader(loader)
        if not normalized_loader:
            return 0
        normalized = {str(value).strip().casefold() for value in loaders if str(value).strip()}
        status = CurseForgeClient._loader_compatibility(loaders, loader)
        if status == "universal":
            return 2
        if normalized_loader in normalized:
            return 0
        if normalized_loader == "quilt" and "fabric" in normalized:
            return 1
        return {"unknown": 3, "unverified": 4}.get(status, 5)

    @staticmethod
    def normalize_release_types(release_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]:
        if release_types is None:
            return ("release", "beta", "alpha")
        values = {str(item).strip().lower() for item in release_types if str(item).strip()}
        output = tuple(item for item in ("release", "beta", "alpha") if item in values)
        return output or ("release",)

    @staticmethod
    def _request_json(method: str, route: str, params: dict[str, object] | None = None, body: object | None = None, ttl: int = 0, force_refresh: bool = False, manual_refresh: bool = False, allow_stale_on_error: bool = True, cache_response: bool = True, namespace: str = "generic") -> CacheLookup:
        normalized_params = {str(key): value for key, value in (params or {}).items() if value not in {None, ""}}
        cache_key = CurseForgeApiCache.make_key(namespace, route, normalized_params, body)
        if cache_response and not force_refresh:
            cached = CurseForgeApiCache.get(cache_key, ttl, allow_stale=False)
            if cached is not None:
                return cached
        if manual_refresh:
            CurseForgeApiCache.assert_manual_refresh_allowed()

        with CurseForgeClient._inflight_guard:
            in_flight = CurseForgeClient._inflight.get(cache_key)
            if in_flight is None:
                in_flight = _InFlightRequest(event=Event())
                CurseForgeClient._inflight[cache_key] = in_flight
                owner = True
            else:
                owner = False
        if not owner:
            if not in_flight.event.wait(CurseForgeClient.REQUEST_TIMEOUT_SECONDS + 10):
                raise RuntimeError("Timed out while waiting for an identical CurseForge request.")
            if in_flight.error is not None:
                raise in_flight.error
            if in_flight.result is None:
                raise RuntimeError("The shared CurseForge request completed without a result.")
            return in_flight.result

        try:
            CurseForgeApiCache.record_attempt(manual=manual_refresh)
            lookup = CurseForgeClient._perform_request(method, route, normalized_params, body, ttl, cache_key, namespace, cache_response)
            in_flight.result = lookup
            return lookup
        except Exception as error:
            retry_after = int(getattr(error, "retry_after_seconds", 0) or 0) or None
            CurseForgeApiCache.record_failure(str(error), retry_after_seconds=retry_after)
            if allow_stale_on_error and cache_response:
                stale = CurseForgeApiCache.get(cache_key, ttl, allow_stale=True)
                if stale is not None:
                    in_flight.result = stale
                    return stale
            in_flight.error = error
            raise
        finally:
            in_flight.event.set()
            with CurseForgeClient._inflight_guard:
                CurseForgeClient._inflight.pop(cache_key, None)

    @staticmethod
    def _perform_request(method: str, route: str, params: dict[str, object], body: object | None, ttl: int, cache_key: str, namespace: str, cache_response: bool) -> CacheLookup:
        headers = {
            "Accept": "application/json",
            "User-Agent": CURSEFORGE_USER_AGENT,
            "X-MCW-Version": VERSION_ID,
        }
        token = CurseForgeConfigManager.client_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        gateways = CurseForgeClient.gateway_urls()
        client = HttpDownloader.get_client()
        last_error: RuntimeError | None = None
        for index, gateway in enumerate(gateways):
            has_fallback = index + 1 < len(gateways)
            try:
                response = client.request(
                    method.upper(),
                    gateway + route,
                    params=params or None,
                    json=body if method.upper() != "GET" else None,
                    headers=headers,
                    timeout=CurseForgeClient.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("response root is not an object")
            except httpx.HTTPStatusError as error:
                converted = CurseForgeClient._gateway_error(error.response)
                if has_fallback and int(error.response.status_code) in CurseForgeClient.FAILOVER_STATUS_CODES:
                    last_error = converted
                    continue
                raise converted from error
            except httpx.HTTPError as error:
                converted = RuntimeError("Unable to contact the configured CurseForge gateway.")
                if has_fallback:
                    last_error = converted
                    continue
                raise converted from error
            except ValueError as error:
                converted = RuntimeError("The configured CurseForge gateway returned invalid JSON.")
                if has_fallback:
                    last_error = converted
                    continue
                raise converted from error

            if cache_response:
                return CurseForgeApiCache.put(cache_key, namespace, payload, ttl)
            return CacheLookup(payload=payload, cache_info=CurseForgeApiCache.status())

        if last_error is not None:
            error = RuntimeError("All configured CurseForge gateways are unavailable.")
            setattr(error, "gateway_failover_attempts", len(gateways))
            setattr(error, "retry_after_seconds", int(getattr(last_error, "retry_after_seconds", 0) or 0))
            raise error from last_error
        raise RuntimeError("No CurseForge gateway is configured. Add at least one protected gateway link in Launcher Settings.")

    @staticmethod
    def _gateway_error(response: httpx.Response) -> RuntimeError:
        status = int(response.status_code)
        code = ""
        message = ""
        request_id = str(response.headers.get("x-request-id") or "").strip()
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            code = str(payload["error"].get("code") or "").strip()
            message = str(payload["error"].get("message") or "").strip()
            request_id = str(payload["error"].get("requestId") or request_id).strip()
        if not message:
            message = f"CurseForge gateway request failed with HTTP {status}."
        if request_id:
            message += f" Request ID: {request_id}."
        error = RuntimeError(message)
        setattr(error, "gateway_status", status)
        retry_after = response.headers.get("retry-after")
        try:
            setattr(error, "retry_after_seconds", max(0, int(retry_after or 0)))
        except ValueError:
            setattr(error, "retry_after_seconds", 0)
        setattr(error, "gateway_error_code", code)
        return error

    @staticmethod
    def _parse_project(data: dict) -> CurseForgeProject:
        authors = tuple(str(item.get("name") or "").strip() for item in data.get("authors", []) if isinstance(item, dict) and str(item.get("name") or "").strip())
        logo = data.get("logo") if isinstance(data.get("logo"), dict) else {}
        links = data.get("links") if isinstance(data.get("links"), dict) else {}
        project_id = int(data.get("id", 0) or 0)
        slug = str(data.get("slug") or "").strip()
        project_url = CurseForgeClient._safe_project_url(links.get("websiteUrl"))
        loader_names = {0: "any", 1: "forge", 2: "cauldron", 3: "liteloader", 4: "fabric", 5: "quilt", 6: "neoforge"}
        indexes = data.get("latestFilesIndexes", []) if isinstance(data.get("latestFilesIndexes"), list) else []
        game_versions = tuple(dict.fromkeys(
            str(item.get("gameVersion") or "").strip()
            for item in indexes
            if isinstance(item, dict) and CurseForgeClient._is_minecraft_version(str(item.get("gameVersion") or ""))
        ))
        loaders = tuple(dict.fromkeys(
            loader_names.get(int(item.get("modLoader", -1) or -1), "")
            for item in indexes
            if isinstance(item, dict) and loader_names.get(int(item.get("modLoader", -1) or -1), "") not in {"", "any"}
        ))
        if not project_url and slug:
            class_id = int(data.get("classId", 0) or 0)
            category = {CurseForgeClient.CLASS_MODPACKS: "modpacks", CurseForgeClient.CLASS_RESOURCE_PACKS: "texture-packs", CurseForgeClient.CLASS_SHADERS: "shaders"}.get(class_id, "mc-mods")
            project_url = f"https://www.curseforge.com/minecraft/{category}/{quote(slug, safe='-')}"
        categories = tuple(
            str(item.get("name") or "").strip()
            for item in data.get("categories", [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
        screenshots = tuple(
            str(item.get("url") or item.get("thumbnailUrl") or "").strip()
            for item in data.get("screenshots", [])
            if isinstance(item, dict) and str(item.get("url") or item.get("thumbnailUrl") or "").strip()
        )
        return CurseForgeProject(
            project_id=project_id,
            name=str(data.get("name") or "Unknown project").strip(),
            slug=slug,
            summary=str(data.get("summary") or "").strip(),
            download_count=int(data.get("downloadCount", 0) or 0),
            authors=authors,
            logo_url=str(logo.get("thumbnailUrl") or logo.get("url") or "").strip(),
            class_id=int(data.get("classId", 0) or 0),
            date_modified=str(data.get("dateModified") or "").strip(),
            project_url=project_url,
            game_versions=game_versions,
            loaders=loaders,
            source_url=str(links.get("sourceUrl") or "").strip(),
            issues_url=str(links.get("issuesUrl") or "").strip(),
            wiki_url=str(links.get("wikiUrl") or "").strip(),
            categories=categories,
            screenshot_urls=screenshots,
            date_created=str(data.get("dateCreated") or "").strip(),
            date_released=str(data.get("dateReleased") or "").strip(),
            status=str(data.get("status") or "").strip(),
            is_featured=bool(data.get("isFeatured", False)),
        )

    @staticmethod
    def _safe_project_url(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        hostname = str(parsed.hostname or "").casefold()
        if parsed.scheme.casefold() != "https":
            return ""
        if hostname != "curseforge.com" and not hostname.endswith(".curseforge.com"):
            return ""
        if parsed.username or parsed.password:
            return ""
        return raw

    @staticmethod
    def _parse_file(data: dict) -> CurseForgeFile:
        hashes = data.get("hashes", []) if isinstance(data.get("hashes"), list) else []
        sha1 = ""
        for item in hashes:
            if isinstance(item, dict) and int(item.get("algo", 0) or 0) == 1:
                sha1 = str(item.get("value") or "").strip().lower()
                break
        dependencies = tuple(
            CurseForgeDependency(
                project_id=int(item.get("modId", 0) or 0),
                relation_type=int(item.get("relationType", 0) or 0),
            )
            for item in data.get("dependencies", [])
            if isinstance(item, dict) and int(item.get("modId", 0) or 0) > 0
        )
        release_type = {1: "release", 2: "beta", 3: "alpha"}.get(int(data.get("releaseType", 1) or 1), "release")
        raw_versions = tuple(str(item).strip() for item in data.get("gameVersions", []) if str(item).strip())
        known_loaders = {"forge", "fabric", "quilt", "neoforge"}
        loaders = tuple(dict.fromkeys(value.casefold() for value in raw_versions if value.casefold() in known_loaders))
        game_versions = tuple(value for value in raw_versions if CurseForgeClient._is_minecraft_version(value))
        return CurseForgeFile(
            file_id=int(data.get("id", 0) or 0),
            project_id=int(data.get("modId", 0) or 0),
            display_name=str(data.get("displayName") or data.get("fileName") or "Unknown file").strip(),
            file_name=Path(str(data.get("fileName") or "download.bin")).name,
            release_type=release_type,
            file_date=str(data.get("fileDate") or "").strip(),
            file_length=max(0, int(data.get("fileLength", 0) or 0)),
            download_url=str(data.get("downloadUrl") or "").strip(),
            sha1=sha1,
            game_versions=game_versions,
            dependencies=dependencies,
            is_available=bool(data.get("isAvailable", True)),
            loaders=loaders,
        )

    @staticmethod
    def _is_minecraft_version(value: str) -> bool:
        normalized = str(value).strip().casefold()
        return bool(
            re.fullmatch(r"\d+\.\d+(?:\.\d+)?(?:[-+._a-z0-9]*)?", normalized)
            or re.fullmatch(r"\d{2}w\d{2}[a-z]", normalized)
        )

    @staticmethod
    def _positive_int(value: int | str, label: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be a positive integer.") from error
        if result <= 0:
            raise ValueError(f"{label} must be a positive integer.")
        return result

    @staticmethod
    def _normalized_ids(values: list[int] | tuple[int, ...] | set[int], label: str) -> tuple[int, ...]:
        output: list[int] = []
        seen: set[int] = set()
        for value in values:
            identifier = CurseForgeClient._positive_int(value, label)
            if identifier not in seen:
                seen.add(identifier)
                output.append(identifier)
        return tuple(output)

    @staticmethod
    def _chunks(values: tuple[int, ...], size: int) -> tuple[tuple[int, ...], ...]:
        return tuple(values[index:index + size] for index in range(0, len(values), size))
