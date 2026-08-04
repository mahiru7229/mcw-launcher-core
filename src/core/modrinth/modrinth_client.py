from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import time
from urllib.parse import quote
import hashlib
import json

import httpx

from src.core.fs.paths import Paths
from src.config import MODRINTH_USER_AGENT
from src.core.mod.provider_game_version_policy import provider_game_version_rank
from src.core.network.httpx_downloader import HttpDownloader
from src.models.modrinth.project import ModrinthProject, ModrinthSearchResult
from src.models.modrinth.version import ModrinthDependency, ModrinthFile, ModrinthVersion


class ModrinthClient:
    BASE_URL = "https://api.modrinth.com/v2"
    CACHE_SCHEMA = 4
    SEARCH_TTL_SECONDS = 10 * 60
    VERSIONS_TTL_SECONDS = 30 * 60
    PROJECT_TTL_SECONDS = 60 * 60
    USER_AGENT = MODRINTH_USER_AGENT

    _cache_locks: dict[Path, Lock] = {}
    _cache_locks_guard = Lock()

    @staticmethod
    def search_projects(project_type: str, query: str = "", game_version: str = "", loader: str = "fabric", index: str = "relevance", offset: int = 0, limit: int = 25, force_refresh: bool = False) -> ModrinthSearchResult:
        normalized_type = str(project_type).strip().lower()
        if normalized_type not in {"mod", "modpack", "resourcepack", "shader"}:
            raise ValueError("Unsupported Modrinth project type.")

        normalized_loader = str(loader).strip().lower()
        normalized_game_version = str(game_version).strip()
        normalized_query = str(query).strip()
        normalized_index = index if index in {"relevance", "downloads", "follows", "newest", "updated"} else "relevance"
        normalized_offset = max(0, int(offset))
        normalized_limit = min(max(1, int(limit)), 100)

        payload = ModrinthClient._search_payload(
            project_type=normalized_type,
            query=normalized_query,
            game_version=normalized_game_version,
            loader=normalized_loader,
            index=normalized_index,
            offset=normalized_offset,
            limit=normalized_limit,
            force_refresh=force_refresh or not normalized_query,
            allow_stale_on_error=True,
        )
        projects = ModrinthClient._projects_from_search_payload(payload)

        # Modrinth's loader facet occasionally returns an empty page for
        # modpack searches even when matching projects exist. Retry without
        # the loader facet, then keep only projects whose search metadata is
        # compatible with the selected loader. Version loading still applies
        # the authoritative loader filter before installation.
        if normalized_type == "modpack" and normalized_loader and not projects:
            fallback_payload = ModrinthClient._search_payload(
                project_type=normalized_type,
                query=normalized_query,
                game_version=normalized_game_version,
                loader="",
                index=normalized_index,
                offset=normalized_offset,
                limit=normalized_limit,
                force_refresh=True,
                allow_stale_on_error=True,
            )
            fallback_projects = ModrinthClient._projects_from_search_payload(fallback_payload)
            compatible_projects = tuple(project for project in fallback_projects if ModrinthClient._project_may_support_loader(project, normalized_loader))
            projects = compatible_projects or fallback_projects
            payload = dict(fallback_payload)
            payload["total_hits"] = len(projects)
            payload["offset"] = normalized_offset
            payload["limit"] = normalized_limit

        if normalized_game_version:
            projects = tuple(
                project
                for _, project in sorted(
                    enumerate(projects),
                    key=lambda pair: (
                        provider_game_version_rank(normalized_game_version, pair[1].versions),
                        pair[0],
                    ),
                )
            )

        if normalized_type == "modpack" and not normalized_query and not projects:
            raise RuntimeError(
                "Modrinth returned no modpacks for the default catalog search. "
                "The API may be unavailable, blocked, or returning an invalid cached response."
            )

        return ModrinthSearchResult(
            projects=projects,
            total_hits=int(payload.get("total_hits", len(projects)) or 0),
            offset=int(payload.get("offset", normalized_offset) or 0),
            limit=int(payload.get("limit", normalized_limit) or normalized_limit),
        )

    @staticmethod
    def _search_payload(project_type: str, query: str, game_version: str, loader: str, index: str, offset: int, limit: int, force_refresh: bool, allow_stale_on_error: bool = True) -> dict:
        facets: list[list[str]] = [[f"project_type:{project_type}"]]
        if loader:
            loader_facets = [f"categories:{item}" for item in ModrinthClient.compatible_loaders(loader)]
            facets.append(loader_facets)
        # Provider game-version labels are advisory. Omitting the strict facet
        # keeps nearby patch builds visible; callers rank them locally.

        payload = ModrinthClient._get_json(
            "/search",
            params={
                "query": query,
                "facets": json.dumps(facets, separators=(",", ":")),
                "index": index,
                "offset": offset,
                "limit": limit,
            },
            ttl=ModrinthClient.SEARCH_TTL_SECONDS,
            force_refresh=force_refresh,
            allow_stale_on_error=allow_stale_on_error,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Modrinth returned an invalid search response.")
        return payload

    @staticmethod
    def _projects_from_search_payload(payload: dict) -> tuple[ModrinthProject, ...]:
        hits = payload.get("hits", [])
        if not isinstance(hits, list):
            return ()
        return tuple(ModrinthClient._parse_project(item) for item in hits if isinstance(item, dict))

    @staticmethod
    def _project_may_support_loader(project: ModrinthProject, loader: str) -> bool:
        normalized_loader = str(loader).strip().lower()
        categories = {str(item).strip().lower() for item in project.categories if str(item).strip()}
        known_loaders = {"fabric", "forge", "neoforge", "quilt"}
        explicit_loaders = categories & known_loaders
        return bool(set(ModrinthClient.compatible_loaders(normalized_loader)) & explicit_loaders) or not explicit_loaders

    @staticmethod
    def get_project(project_id: str, force_refresh: bool = False) -> ModrinthProject:
        identifier = ModrinthClient._required(project_id, "Project ID")
        payload = ModrinthClient._get_json(f"/project/{quote(identifier, safe='')}", ttl=ModrinthClient.PROJECT_TTL_SECONDS, force_refresh=force_refresh)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Modrinth project '{identifier}' is unavailable.")
        return ModrinthClient._parse_project(payload)

    @staticmethod
    def list_project_versions(project_id: str, loader: str = "fabric", game_version: str = "", version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False) -> list[ModrinthVersion]:
        identifier = ModrinthClient._required(project_id, "Project ID")
        params: dict[str, str] = {"include_changelog": "false"}
        if loader:
            params["loaders"] = json.dumps(list(ModrinthClient.compatible_loaders(loader)), separators=(",", ":"))
        payload = ModrinthClient._get_json(f"/project/{quote(identifier, safe='')}/version", params=params, ttl=ModrinthClient.VERSIONS_TTL_SECONDS, force_refresh=force_refresh)
        if not isinstance(payload, list):
            raise RuntimeError(f"Modrinth versions for '{identifier}' are unavailable.")
        versions = [ModrinthClient._parse_version(item) for item in payload if isinstance(item, dict)]
        allowed_types = ModrinthClient.normalize_version_types(version_types)
        versions = [version for version in versions if version.version_type in allowed_types]
        versions.sort(key=ModrinthClient._version_sort_key, reverse=True)
        versions.sort(key=lambda version: ModrinthClient._loader_rank(version.loaders, loader))
        versions.sort(key=lambda version: provider_game_version_rank(game_version, version.game_versions))
        return versions

    @staticmethod
    def get_version(version_id: str, force_refresh: bool = False) -> ModrinthVersion:
        identifier = ModrinthClient._required(version_id, "Version ID")
        payload = ModrinthClient._get_json(f"/version/{quote(identifier, safe='')}", ttl=ModrinthClient.VERSIONS_TTL_SECONDS, force_refresh=force_refresh)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Modrinth version '{identifier}' is unavailable.")
        return ModrinthClient._parse_version(payload)

    @staticmethod
    def select_version(project_id: str, game_version: str, loader: str = "fabric", version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> ModrinthVersion:
        versions = ModrinthClient.list_project_versions(project_id, loader=loader, game_version=game_version, version_types=version_types)
        if not versions:
            raise RuntimeError(f"No allowed {loader.title()} version of this project is available.")
        return versions[0]


    @staticmethod
    def compatible_loaders(loader: str) -> tuple[str, ...]:
        normalized = str(loader).strip().casefold()
        if normalized == "quilt":
            return "quilt", "fabric"
        return (normalized,) if normalized else ()

    @staticmethod
    def _loader_rank(loaders: tuple[str, ...] | list[str] | set[str], loader: str) -> int:
        normalized = {str(item).strip().casefold() for item in loaders if str(item).strip()}
        requested = str(loader).strip().casefold()
        if not requested:
            return 0
        if requested in normalized:
            return 0
        if requested == "quilt" and "fabric" in normalized:
            return 1
        return 2

    @staticmethod
    def normalize_version_types(version_types: tuple[str, ...] | list[str] | set[str] | None = None) -> tuple[str, ...]:
        if version_types is None:
            return ("release", "beta", "alpha")
        normalized = {str(item).strip().lower() for item in version_types if str(item).strip()}
        allowed = tuple(item for item in ("release", "beta", "alpha") if item in normalized)
        return allowed or ("release",)

    @staticmethod
    def _version_sort_key(version: ModrinthVersion) -> tuple[float, int, int]:
        type_weight = {"release": 3, "beta": 2, "alpha": 1}.get(version.version_type, 0)
        return ModrinthClient._published_timestamp(version.date_published), int(version.featured), type_weight

    @staticmethod
    def _published_timestamp(value: str) -> float:
        normalized = str(value).strip()
        if not normalized:
            return 0.0
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    @staticmethod
    def _parse_project(data: dict) -> ModrinthProject:
        project_id = str(data.get("project_id") or data.get("id") or "").strip()
        slug = str(data.get("slug") or project_id).strip()
        project_type = str(data.get("project_type") or "mod").strip().lower()
        license_data = data.get("license") if isinstance(data.get("license"), dict) else {}
        gallery = data.get("gallery") if isinstance(data.get("gallery"), list) else []
        gallery_urls = tuple(
            str(item.get("url") or "").strip()
            for item in gallery
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        )
        loaders = tuple(str(item).strip().lower() for item in data.get("loaders", []) if str(item).strip())
        categories = tuple(str(item) for item in data.get("categories", []) if str(item).strip())
        if not loaders:
            known_loaders = {"fabric", "forge", "neoforge", "quilt"}
            loaders = tuple(item.casefold() for item in categories if item.casefold() in known_loaders)
        project_url = f"https://modrinth.com/{quote(project_type, safe='')}/{quote(slug, safe='-')}" if slug else ""
        return ModrinthProject(
            project_id=project_id,
            slug=slug,
            title=str(data.get("title") or data.get("name") or project_id or "Unknown project").strip(),
            description=str(data.get("description") or "").strip(),
            project_type=project_type,
            author=str(data.get("author") or "").strip(),
            downloads=int(data.get("downloads", 0) or 0),
            icon_url=str(data.get("icon_url") or "").strip(),
            categories=categories,
            versions=tuple(str(item) for item in data.get("versions", []) if str(item).strip()),
            latest_version=str(data.get("latest_version") or "").strip(),
            client_side=str(data.get("client_side") or "unknown").strip().lower(),
            server_side=str(data.get("server_side") or "unknown").strip().lower(),
            date_modified=str(data.get("date_modified") or data.get("updated") or "").strip(),
            body=str(data.get("body") or "").strip(),
            project_url=project_url,
            source_url=str(data.get("source_url") or "").strip(),
            issues_url=str(data.get("issues_url") or "").strip(),
            wiki_url=str(data.get("wiki_url") or "").strip(),
            discord_url=str(data.get("discord_url") or "").strip(),
            license_id=str(license_data.get("id") or "").strip(),
            license_name=str(license_data.get("name") or "").strip(),
            license_url=str(license_data.get("url") or "").strip(),
            followers=int(data.get("followers", 0) or 0),
            date_published=str(data.get("published") or "").strip(),
            gallery_urls=gallery_urls,
            loaders=loaders,
        )

    @staticmethod
    def _parse_version(data: dict) -> ModrinthVersion:
        files: list[ModrinthFile] = []
        for item in data.get("files", []):
            if not isinstance(item, dict):
                continue
            hashes = item.get("hashes", {}) if isinstance(item.get("hashes"), dict) else {}
            files.append(ModrinthFile(url=str(item.get("url") or "").strip(), filename=str(item.get("filename") or "").strip(), sha1=str(hashes.get("sha1") or "").strip().lower(), sha512=str(hashes.get("sha512") or "").strip().lower(), size=int(item.get("size", 0) or 0), primary=bool(item.get("primary", False))))

        dependencies: list[ModrinthDependency] = []
        for item in data.get("dependencies", []):
            if not isinstance(item, dict):
                continue
            dependencies.append(ModrinthDependency(dependency_type=str(item.get("dependency_type") or "required").strip().lower(), project_id=str(item.get("project_id") or "").strip(), version_id=str(item.get("version_id") or "").strip(), file_name=str(item.get("file_name") or "").strip()))

        return ModrinthVersion(
            version_id=str(data.get("id") or "").strip(),
            project_id=str(data.get("project_id") or "").strip(),
            name=str(data.get("name") or data.get("version_number") or "Unknown version").strip(),
            version_number=str(data.get("version_number") or data.get("name") or "Unknown").strip(),
            version_type=str(data.get("version_type") or "release").strip().lower(),
            game_versions=tuple(str(item) for item in data.get("game_versions", []) if str(item).strip()),
            loaders=tuple(str(item).lower() for item in data.get("loaders", []) if str(item).strip()),
            files=tuple(files),
            dependencies=tuple(dependencies),
            featured=bool(data.get("featured", False)),
            date_published=str(data.get("date_published") or "").strip(),
        )

    @staticmethod
    def _get_json(path: str, params: dict[str, object] | None = None, ttl: int = 0, force_refresh: bool = False, allow_stale_on_error: bool = True) -> object:
        normalized_params = {str(key): value for key, value in (params or {}).items() if value not in {None, ""}}
        cache_key = json.dumps({"path": path, "params": normalized_params}, sort_keys=True, separators=(",", ":"))
        cache_path = Paths.modrinth_api_cache(hashlib.sha256(cache_key.encode("utf-8")).hexdigest())

        with ModrinthClient._get_cache_lock(cache_path):
            cached = ModrinthClient._read_cache(cache_path)
            cached_payload = cached.get("payload") if cached is not None else None
            cached_is_usable = ModrinthClient._cached_payload_is_usable(path, normalized_params, cached_payload)
            if cached is not None and cached_is_usable and not force_refresh:
                try:
                    age = time() - float(cached.get("fetchedAt", 0) or 0)
                except (TypeError, ValueError):
                    age = float("inf")
                if age <= ttl:
                    return cached_payload

            client = HttpDownloader.get_client()
            try:
                response = client.get(
                    ModrinthClient.BASE_URL + path,
                    params=normalized_params,
                    headers={"User-Agent": ModrinthClient.USER_AGENT, "Accept": "application/json"},
                    timeout=20.0,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as error:
                if allow_stale_on_error and cached_is_usable:
                    return cached_payload
                status = int(error.response.status_code)
                raise RuntimeError(f"Modrinth API request failed with HTTP {status}.") from error
            except httpx.HTTPError as error:
                if allow_stale_on_error and cached_is_usable:
                    return cached_payload
                raise RuntimeError(f"Unable to contact Modrinth: {error}") from error
            except ValueError as error:
                if allow_stale_on_error and cached_is_usable:
                    return cached_payload
                raise RuntimeError("Modrinth returned an invalid JSON response.") from error

            ModrinthClient._write_cache(cache_path, payload)
            return payload

    @staticmethod
    def _cached_payload_is_usable(path: str, params: dict[str, object], payload: object) -> bool:
        if payload is None:
            return False
        if path != "/search":
            return True
        if not isinstance(payload, dict):
            return False
        hits = payload.get("hits")
        if not isinstance(hits, list):
            return False
        # Empty search results are meaningful only when received live. They
        # are never useful as an offline fallback because they make network
        # failures look like a successful search with zero projects.
        return bool(hits)

    @staticmethod
    def _get_cache_lock(path: Path) -> Lock:
        try:
            normalized = path.resolve(strict=False)
        except OSError:
            normalized = path.absolute()
        with ModrinthClient._cache_locks_guard:
            return ModrinthClient._cache_locks.setdefault(normalized, Lock())

    @staticmethod
    def _read_cache(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("schemaVersion") != ModrinthClient.CACHE_SCHEMA or "payload" not in data:
            return None
        return data

    @staticmethod
    def _write_cache(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_text(json.dumps({"schemaVersion": ModrinthClient.CACHE_SCHEMA, "fetchedAt": time(), "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _required(value: str, label: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"{label} is required.")
        return normalized
