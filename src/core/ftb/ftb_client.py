from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx

from src.config import FTB_USER_AGENT
from src.core.ftb.ftb_cache import FTBApiCache, FTBApiCacheLookup
from src.core.network.httpx_downloader import HttpDownloader
from src.models.ftb.cache import FTBCacheInfo
from src.models.ftb.project import FTBProject, FTBSearchResult
from src.models.ftb.version import FTBFile, FTBTarget, FTBVersion, FTBVersionSummary


class FTBClient:
    """Small public FTB modpack API adapter.

    The FTB feeds have historically exposed both a public catalog prefix and a
    direct modpack prefix. Requests therefore use ordered official endpoints
    and only fail after every compatible route has been attempted.
    """

    PUBLIC_BASE_URL = "https://api.feed-the-beast.com/v1/modpacks/public"
    DIRECT_BASE_URL = "https://api.feed-the-beast.com/v1/modpacks"
    BASE_URLS = (PUBLIC_BASE_URL, DIRECT_BASE_URL)
    SEARCH_TTL_SECONDS = 5 * 60
    PROJECT_TTL_SECONDS = 15 * 60
    VERSION_TTL_SECONDS = 30 * 60
    REQUEST_TIMEOUT_SECONDS = 20.0
    MAX_SEARCH_FETCH = 100
    FAILOVER_STATUS_CODES = frozenset({404, 408, 425, 429, *range(500, 600)})

    @staticmethod
    def api_cache_status() -> FTBCacheInfo:
        return FTBApiCache.status()

    @staticmethod
    def clear_api_cache() -> None:
        FTBApiCache.clear()

    @staticmethod
    def cache_status() -> FTBCacheInfo:
        """Compatibility alias for the pre-v1.3 API-cache name."""
        return FTBClient.api_cache_status()

    @staticmethod
    def clear_cache() -> None:
        """Compatibility alias; clears provider API metadata only."""
        FTBClient.clear_api_cache()

    @staticmethod
    def search_projects(query: str = "", index: int = 0, page_size: int = 25, sort: str = "popularity", force_refresh: bool = False) -> FTBSearchResult:
        normalized_query = " ".join(str(query).split())
        normalized_page_size = min(max(1, int(page_size)), 50)
        normalized_index = max(0, int(index))
        fetch_limit = min(FTBClient.MAX_SEARCH_FETCH, max(normalized_page_size, normalized_index + normalized_page_size))
        if normalized_query:
            path = f"/modpack/search/{fetch_limit}"
            params = {"term": normalized_query}
            namespace = "search"
        else:
            path = f"/modpack/popular/installs/{fetch_limit}"
            params = {}
            namespace = "popular"
        lookup = FTBClient._request_json(path, params=params, ttl=FTBClient.SEARCH_TTL_SECONDS, force_refresh=force_refresh, allow_stale_on_error=True, namespace=namespace)
        identifiers, embedded = FTBClient._search_entries(lookup.payload)
        projects_by_id: dict[int, FTBProject] = {}
        for item in embedded:
            project = FTBClient._parse_project(item)
            if project.project_id > 0 and not project.private:
                projects_by_id[project.project_id] = project
        for identifier in identifiers:
            if identifier in projects_by_id:
                continue
            try:
                project = FTBClient.get_project(identifier, force_refresh=force_refresh)
            except RuntimeError:
                continue
            if not project.private:
                projects_by_id[project.project_id] = project
        projects = list(projects_by_id.values())
        normalized_sort = str(sort or "popularity").strip().casefold()
        if normalized_sort == "updated":
            projects.sort(key=lambda item: (item.updated_at, item.project_id), reverse=True)
        elif normalized_sort == "newest":
            projects.sort(key=lambda item: (item.created_at, item.project_id), reverse=True)
        elif normalized_sort == "name":
            projects.sort(key=lambda item: item.name.casefold())
        else:
            projects.sort(key=lambda item: (item.plays, item.project_id), reverse=True)
        page = tuple(projects[normalized_index : normalized_index + normalized_page_size])
        return FTBSearchResult(
            projects=page,
            total_count=len(projects),
            index=normalized_index,
            page_size=normalized_page_size,
            cache_info=lookup.cache_info,
        )

    @staticmethod
    def get_project(project_id: int | str, force_refresh: bool = False) -> FTBProject:
        identifier = FTBClient._positive_int(project_id, "FTB project ID")
        lookup = FTBClient._request_json(
            f"/modpack/{identifier}",
            ttl=FTBClient.PROJECT_TTL_SECONDS,
            force_refresh=force_refresh,
            allow_stale_on_error=True,
            namespace="project",
        )
        payload = FTBClient._unwrap_payload(lookup.payload)
        if not isinstance(payload, dict):
            raise RuntimeError(f"FTB modpack {identifier} is unavailable.")
        project = FTBClient._parse_project(payload)
        if project.project_id <= 0:
            raise RuntimeError(f"FTB modpack {identifier} returned invalid metadata.")
        return project

    @staticmethod
    def get_project_details(project_id: int | str, force_refresh: bool = False) -> FTBProject:
        return FTBClient.get_project(project_id, force_refresh=force_refresh)

    @staticmethod
    def list_versions(project_id: int | str, release_types: Iterable[str] | None = None, force_refresh: bool = False) -> tuple[FTBVersionSummary, ...]:
        project = FTBClient.get_project(project_id, force_refresh=force_refresh)
        allowed = FTBClient._normalized_release_types(release_types)
        versions = [
            version for version in project.versions
            if version.release_type in allowed and not version.private
        ]
        # FTB feeds are not consistent about version ordering.  Always present
        # the newest entry first, preferring the provider update timestamp and
        # using the monotonically increasing version ID as a stable fallback.
        versions.sort(key=lambda version: (int(version.updated or 0), int(version.version_id or 0)), reverse=True)
        return tuple(versions)

    @staticmethod
    def get_version(project_id: int | str, version_id: int | str, force_refresh: bool = False) -> FTBVersion:
        project_identifier = FTBClient._positive_int(project_id, "FTB project ID")
        version_identifier = FTBClient._positive_int(version_id, "FTB version ID")
        lookup = FTBClient._request_json(
            f"/modpack/{project_identifier}/{version_identifier}",
            ttl=FTBClient.VERSION_TTL_SECONDS,
            force_refresh=force_refresh,
            allow_stale_on_error=True,
            namespace="version",
        )
        payload = FTBClient._unwrap_payload(lookup.payload)
        if not isinstance(payload, dict):
            raise RuntimeError(f"FTB modpack version {version_identifier} is unavailable.")
        return FTBClient._parse_version(project_identifier, payload)

    @staticmethod
    def _request_json(path: str, params: dict[str, object] | None = None, ttl: int = 0, force_refresh: bool = False, allow_stale_on_error: bool = False, namespace: str = "api") -> FTBApiCacheLookup:
        normalized_path = "/" + str(path).lstrip("/")
        normalized_params = dict(params or {})
        cache_key = FTBApiCache.make_key(namespace, normalized_path, normalized_params)
        if not force_refresh:
            cached = FTBApiCache.get(cache_key, ttl)
            if cached is not None:
                return cached
        errors: list[str] = []
        client = HttpDownloader.get_client()
        headers = {"User-Agent": FTB_USER_AGENT, "Accept": "application/json"}
        for base in FTBClient.BASE_URLS:
            url = base.rstrip("/") + normalized_path
            try:
                response = client.get(url, params=normalized_params or None, headers=headers, timeout=FTBClient.REQUEST_TIMEOUT_SECONDS)
                if response.status_code in FTBClient.FAILOVER_STATUS_CODES:
                    errors.append(f"{response.status_code} from {url}")
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, (dict, list)):
                    raise RuntimeError("FTB returned a non-object JSON response.")
                error_message = FTBClient._payload_error(payload)
                if error_message:
                    raise RuntimeError(error_message)
                return FTBApiCache.put(cache_key, namespace, payload, ttl)
            except (httpx.HTTPError, ValueError, RuntimeError) as error:
                errors.append(str(error) or type(error).__name__)
                continue
        detail = "; ".join(dict.fromkeys(value for value in errors if value)) or "No official FTB API endpoint responded."
        FTBApiCache.record_failure(detail)
        if allow_stale_on_error:
            stale = FTBApiCache.get(cache_key, ttl, allow_stale=True)
            if stale is not None:
                return stale
        raise RuntimeError(f"Could not contact the FTB modpack service: {detail}")

    @staticmethod
    def _search_entries(payload: object) -> tuple[tuple[int, ...], tuple[dict, ...]]:
        unwrapped = FTBClient._unwrap_payload(payload)
        raw: object = unwrapped
        if isinstance(unwrapped, dict):
            for key in ("packs", "modpacks", "results", "data"):
                candidate = unwrapped.get(key)
                if isinstance(candidate, list):
                    raw = candidate
                    break
        if not isinstance(raw, list):
            return (), ()
        identifiers: list[int] = []
        embedded: list[dict] = []
        for item in raw:
            if isinstance(item, dict):
                embedded.append(item)
                identifier = FTBClient._int(item.get("id") or item.get("packId") or item.get("pack_id"))
                if identifier > 0:
                    identifiers.append(identifier)
            else:
                identifier = FTBClient._int(item)
                if identifier > 0:
                    identifiers.append(identifier)
        return tuple(dict.fromkeys(identifiers)), tuple(embedded)

    @staticmethod
    def _parse_project(data: dict) -> FTBProject:
        identifier = FTBClient._int(data.get("id") or data.get("packId") or data.get("pack_id"))
        versions = tuple(
            summary for summary in (FTBClient._parse_version_summary(item) for item in FTBClient._list(data.get("versions")))
            if summary.version_id > 0
        )
        authors = FTBClient._authors(data)
        art_urls = FTBClient._art_urls(data)
        updated_epoch = max((summary.updated for summary in versions), default=FTBClient._int(data.get("updated") or data.get("dateModified")))
        created = FTBClient._date_text(data.get("created") or data.get("dateCreated"))
        updated = FTBClient._date_text(data.get("updated") or data.get("dateModified") or updated_epoch)
        synopsis = FTBClient._text(data.get("synopsis") or data.get("shortDescription") or data.get("summary") or data.get("notification"))
        description = FTBClient._description(data)
        tags = tuple(dict.fromkeys(FTBClient._string_values(data.get("tags") or data.get("categories"))))
        website = FTBClient._website(data)
        icon = FTBClient._icon_url(data, art_urls)
        gallery = tuple(url for url in art_urls if url and url != icon)
        return FTBProject(
            project_id=identifier,
            name=FTBClient._text(data.get("name")) or f"FTB Modpack {identifier}",
            synopsis=synopsis,
            description=description or synopsis,
            authors=authors,
            icon_url=icon,
            gallery_urls=gallery,
            tags=tags,
            plays=max(0, FTBClient._int(data.get("installs") or data.get("plays") or data.get("downloads"))),
            updated_at=updated,
            created_at=created,
            website_url=website or (f"https://www.feed-the-beast.com/modpacks/{identifier}" if identifier > 0 else ""),
            versions=versions,
            private=bool(data.get("private", False)),
            status=FTBClient._text(data.get("status")),
        )

    @staticmethod
    def _parse_version_summary(data: object) -> FTBVersionSummary:
        if not isinstance(data, dict):
            return FTBVersionSummary(0, "", "release", 0, False)
        return FTBVersionSummary(
            version_id=FTBClient._int(data.get("id") or data.get("versionId")),
            name=FTBClient._text(data.get("name") or data.get("version")),
            release_type=FTBClient.normalize_release_type(data.get("type") or data.get("releaseType")),
            updated=FTBClient._int(data.get("updated")),
            private=bool(data.get("private", False)),
            targets=tuple(FTBClient._parse_target(item) for item in FTBClient._list(data.get("targets")) if isinstance(item, dict)),
        )

    @staticmethod
    def _parse_version(project_id: int, data: dict) -> FTBVersion:
        specs = data.get("specs") if isinstance(data.get("specs"), dict) else {}
        files = tuple(
            file for file in (FTBClient._parse_file(item) for item in FTBClient._list(data.get("files")))
            if file.file_id > 0 and file.name
        )
        targets = tuple(FTBClient._parse_target(item) for item in FTBClient._list(data.get("targets")) if isinstance(item, dict))
        identifier = FTBClient._int(data.get("id") or data.get("versionId"))
        if identifier <= 0:
            raise RuntimeError("FTB returned an invalid modpack version ID.")
        return FTBVersion(
            project_id=project_id,
            version_id=identifier,
            name=FTBClient._text(data.get("name") or data.get("version")) or str(identifier),
            release_type=FTBClient.normalize_release_type(data.get("type") or data.get("releaseType")),
            files=files,
            targets=targets,
            status=FTBClient._text(data.get("status")),
            notification=FTBClient._text(data.get("notification") or data.get("message")),
            minimum_memory_mb=max(0, FTBClient._int(specs.get("minimum"))),
            recommended_memory_mb=max(0, FTBClient._int(specs.get("recommended"))),
        )

    @staticmethod
    def _parse_target(data: dict) -> FTBTarget:
        return FTBTarget(
            target_id=FTBClient._int(data.get("id")),
            target_type=FTBClient._text(data.get("type")).casefold(),
            name=FTBClient._text(data.get("name")),
            version=FTBClient._text(data.get("version")),
            updated=FTBClient._int(data.get("updated")),
        )

    @staticmethod
    def _parse_file(data: object) -> FTBFile:
        if not isinstance(data, dict):
            return FTBFile(0, "", "", "", "", (), "", 0)
        urls = tuple(dict.fromkeys(
            value for value in (
                FTBClient._text(data.get("url")),
                *FTBClient._string_values(data.get("mirrors")),
            ) if value
        ))
        return FTBFile(
            file_id=FTBClient._int(data.get("id")),
            name=FTBClient._text(data.get("name")),
            path=FTBClient._text(data.get("path")),
            version=FTBClient._text(data.get("version")),
            file_type=FTBClient._text(data.get("type")),
            urls=urls,
            sha1=FTBClient._text(data.get("sha1")).casefold(),
            size=max(0, FTBClient._int(data.get("size"))),
            client_only=bool(data.get("clientonly", data.get("clientOnly", False))),
            server_only=bool(data.get("serveronly", data.get("serverOnly", False))),
            optional=bool(data.get("optional", False)),
        )

    @staticmethod
    def normalize_release_type(value: object) -> str:
        normalized = FTBClient._text(value).casefold()
        if normalized in {"alpha", "experimental", "dev", "development", "3"}:
            return "alpha"
        if normalized in {"beta", "preview", "2"}:
            return "beta"
        return "release"

    @staticmethod
    def normalize_loader(value: object) -> str:
        normalized = FTBClient._text(value).casefold().replace(" ", "")
        aliases = {
            "fabric": "fabric",
            "fabricloader": "fabric",
            "forge": "forge",
            "minecraftforge": "forge",
            "neoforge": "neoforge",
            "neo-forge": "neoforge",
            "quilt": "quilt",
            "quiltloader": "quilt",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _normalized_release_types(values: Iterable[str] | None) -> frozenset[str]:
        normalized = {FTBClient.normalize_release_type(value) for value in (values or ("release",))}
        normalized.add("release")
        return frozenset(normalized)

    @staticmethod
    def _unwrap_payload(payload: object) -> object:
        if isinstance(payload, dict):
            for key in ("data", "result"):
                value = payload.get(key)
                if isinstance(value, (dict, list)) and len(payload) <= 4:
                    return value
        return payload

    @staticmethod
    def _payload_error(payload: object) -> str:
        if not isinstance(payload, dict):
            return ""
        if payload.get("ok") is False or str(payload.get("status") or "").casefold() in {"error", "failed"}:
            return FTBClient._text(payload.get("message") or payload.get("error")) or "FTB rejected the request."
        return ""

    @staticmethod
    def _description(data: dict) -> str:
        value = data.get("description") or data.get("descriptionHtml") or data.get("longDescription")
        if isinstance(value, dict):
            value = value.get("html") or value.get("text") or value.get("content")
        return FTBClient._text(value)

    @staticmethod
    def _authors(data: dict) -> tuple[str, ...]:
        values: list[str] = []
        for raw in (data.get("authors"), data.get("author"), data.get("team"), data.get("developer")):
            if isinstance(raw, dict):
                raw = raw.get("name") or raw.get("username") or raw.get("displayName")
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        item = item.get("name") or item.get("username") or item.get("displayName")
                    text = FTBClient._text(item)
                    if text:
                        values.append(text)
            else:
                text = FTBClient._text(raw)
                if text:
                    values.append(text)
        return tuple(dict.fromkeys(values)) or ("Feed The Beast",)

    @staticmethod
    def _art_urls(data: dict) -> tuple[str, ...]:
        values: list[str] = []
        for key in ("art", "artwork", "images", "gallery", "screenshots"):
            for item in FTBClient._list(data.get(key)):
                if isinstance(item, dict):
                    value = item.get("url") or item.get("src") or item.get("image")
                else:
                    value = item
                text = FTBClient._text(value)
                if text.startswith("https://"):
                    values.append(text)
        for key in ("icon", "iconUrl", "logo", "logoUrl", "thumbnail", "thumbnailUrl"):
            raw = data.get(key)
            if isinstance(raw, dict):
                raw = raw.get("url") or raw.get("src")
            text = FTBClient._text(raw)
            if text.startswith("https://"):
                values.insert(0, text)
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _icon_url(data: dict, art_urls: tuple[str, ...]) -> str:
        for key in ("icon", "iconUrl", "logo", "logoUrl", "thumbnail", "thumbnailUrl"):
            raw = data.get(key)
            if isinstance(raw, dict):
                raw = raw.get("url") or raw.get("src")
            value = FTBClient._text(raw)
            if value.startswith("https://"):
                return value
        art = FTBClient._list(data.get("art") or data.get("artwork") or data.get("images"))
        for item in art:
            if not isinstance(item, dict):
                continue
            art_type = FTBClient._text(item.get("type") or item.get("name")).casefold()
            value = FTBClient._text(item.get("url") or item.get("src"))
            if value.startswith("https://") and any(token in art_type for token in ("square", "icon", "logo", "thumbnail")):
                return value
        return art_urls[0] if art_urls else ""

    @staticmethod
    def _website(data: dict) -> str:
        for key in ("website", "websiteUrl", "url", "link"):
            raw = data.get(key)
            if isinstance(raw, dict):
                raw = raw.get("url") or raw.get("href")
            text = FTBClient._text(raw)
            if text.startswith("https://"):
                return text
        links = data.get("links")
        if isinstance(links, dict):
            for key in ("website", "project", "homepage"):
                text = FTBClient._text(links.get(key))
                if text.startswith("https://"):
                    return text
        return ""

    @staticmethod
    def _string_values(value: object) -> tuple[str, ...]:
        output: list[str] = []
        for item in FTBClient._list(value):
            if isinstance(item, dict):
                item = item.get("name") or item.get("value") or item.get("label")
            text = FTBClient._text(item)
            if text:
                output.append(text)
        return tuple(dict.fromkeys(output))

    @staticmethod
    def _list(value: object) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return []

    @staticmethod
    def _date_text(value: object) -> str:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            timestamp = FTBClient._int(value)
            if timestamp > 10_000_000_000:
                timestamp //= 1000
            if timestamp > 0:
                try:
                    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                except (OverflowError, OSError, ValueError):
                    return ""
        return FTBClient._text(value)

    @staticmethod
    def _positive_int(value: object, label: str) -> int:
        result = FTBClient._int(value)
        if result <= 0:
            raise ValueError(f"{label} must be a positive integer.")
        return result

    @staticmethod
    def _int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()
