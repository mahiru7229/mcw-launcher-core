from pathlib import Path

import httpx

from src.config import FTB_USER_AGENT
from src.core.ftb.ftb_cache import FTBCache
from src.core.ftb.ftb_client import FTBClient
from src.core.network.httpx_downloader import HttpDownloader


def configure_client(monkeypatch, tmp_path: Path, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: client))
    monkeypatch.setattr(FTBCache, "root", staticmethod(lambda: tmp_path))
    return client


def project_payload(project_id: int = 25) -> dict:
    return {
        "id": project_id,
        "name": "FTB Example",
        "synopsis": "A compact test pack",
        "description": "<p>Full description</p>",
        "authors": [{"name": "FTB Team"}],
        "installs": 12345,
        "icon": "https://cdn.example/icon.png",
        "art": [{"type": "screenshot", "url": "https://cdn.example/screen.png"}],
        "versions": [
            {
                "id": 101,
                "name": "1.0.0",
                "type": "release",
                "updated": 1760000000,
                "private": False,
                "targets": [
                    {"id": 1, "type": "game", "name": "minecraft", "version": "1.20.1"},
                    {"id": 2, "type": "modloader", "name": "forge", "version": "47.4.0"},
                ],
            },
            {"id": 102, "name": "1.1.0-beta", "type": "beta", "updated": 1761000000, "private": False},
        ],
    }


def version_payload(project_id: int = 25, version_id: int = 101) -> dict:
    return {
        "id": version_id,
        "name": "1.0.0",
        "type": "release",
        "status": "public",
        "specs": {"minimum": 4096, "recommended": 6144},
        "targets": [
            {"id": 1, "type": "game", "name": "minecraft", "version": "1.20.1"},
            {"id": 2, "type": "modloader", "name": "forge", "version": "47.4.0"},
            {"id": 3, "type": "runtime", "name": "java", "version": "17"},
        ],
        "files": [
            {
                "id": 500,
                "name": "example.jar",
                "path": "mods",
                "version": "1.0.0",
                "type": "mod",
                "url": "https://primary.example/example.jar",
                "mirrors": ["https://mirror.example/example.jar", "https://primary.example/example.jar"],
                "sha1": "a" * 40,
                "size": 123,
                "clientonly": True,
                "serveronly": False,
                "optional": False,
            }
        ],
    }


def test_project_and_version_use_official_routes_and_parse_manifest(monkeypatch, tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/modpack/25/101"):
            return httpx.Response(200, request=request, json=version_payload())
        if request.url.path.endswith("/modpack/25"):
            return httpx.Response(200, request=request, json=project_payload())
        return httpx.Response(404, request=request)

    client = configure_client(monkeypatch, tmp_path, handler)
    project = FTBClient.get_project(25, force_refresh=True)
    version = FTBClient.get_version(25, 101, force_refresh=True)

    assert requests[0].url.path == "/v1/modpacks/public/modpack/25"
    assert requests[0].headers["user-agent"] == FTB_USER_AGENT
    assert project.name == "FTB Example"
    assert project.authors == ("FTB Team",)
    assert project.icon_url == "https://cdn.example/icon.png"
    assert project.versions[0].minecraft_version == "1.20.1"
    assert project.versions[0].loader == "forge"
    assert version.minecraft_version == "1.20.1"
    assert version.loader == "forge"
    assert version.loader_version == "47.4.0"
    assert version.java_version == "17"
    assert version.recommended_memory_mb == 6144
    assert version.files[0].urls == (
        "https://primary.example/example.jar",
        "https://mirror.example/example.jar",
    )
    assert version.files[0].sha1 == "a" * 40
    client.close()


def test_request_fails_over_from_public_to_direct_official_endpoint(monkeypatch, tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if "/public/" in request.url.path:
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request, json=project_payload())

    client = configure_client(monkeypatch, tmp_path, handler)
    project = FTBClient.get_project(25, force_refresh=True)

    assert project.project_id == 25
    assert paths == [
        "/v1/modpacks/public/modpack/25",
        "/v1/modpacks/modpack/25",
    ]
    client.close()


def test_popular_search_accepts_ids_and_uses_project_cache(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/popular/installs/25"):
            return httpx.Response(200, request=request, json={"packs": [25]})
        if request.url.path.endswith("/modpack/25"):
            return httpx.Response(200, request=request, json=project_payload())
        return httpx.Response(404, request=request)

    client = configure_client(monkeypatch, tmp_path, handler)
    first = FTBClient.search_projects(force_refresh=False)
    second = FTBClient.search_projects(force_refresh=False)

    assert first.projects[0].project_id == 25
    assert second.projects[0].project_id == 25
    assert calls.count("/v1/modpacks/public/modpack/popular/installs/25") == 1
    assert calls.count("/v1/modpacks/public/modpack/25") == 1
    assert second.cache_info.from_cache is True
    client.close()


def test_search_filters_private_projects_and_release_channels(monkeypatch, tmp_path: Path) -> None:
    public = project_payload(25)
    private = project_payload(26)
    private["private"] = True

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/25"):
            assert request.url.params["term"] == "example"
            return httpx.Response(200, request=request, json={"packs": [public, private]})
        if request.url.path.endswith("/modpack/25"):
            return httpx.Response(200, request=request, json=public)
        return httpx.Response(404, request=request)

    client = configure_client(monkeypatch, tmp_path, handler)
    result = FTBClient.search_projects("example", force_refresh=True)
    versions = FTBClient.list_versions(25, ("release", "beta"), force_refresh=False)

    assert [project.project_id for project in result.projects] == [25]
    assert [version.release_type for version in versions] == ["beta", "release"]
    client.close()


def test_stale_cache_is_returned_when_both_official_endpoints_fail(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, request=request, json=project_payload())
        return httpx.Response(503, request=request, json={"message": "maintenance"})

    client = configure_client(monkeypatch, tmp_path, handler)
    first = FTBClient.get_project(25)
    fallback = FTBClient.get_project(25, force_refresh=True)

    assert first.project_id == fallback.project_id == 25
    assert FTBClient.cache_status().last_error
    client.close()


def test_list_versions_uses_version_id_as_newest_fallback(monkeypatch) -> None:
    versions = (
        FTBClient._parse_version_summary({"id": 100, "name": "Old", "type": "release", "updated": 0}),
        FTBClient._parse_version_summary({"id": 300, "name": "New", "type": "release", "updated": 0}),
        FTBClient._parse_version_summary({"id": 200, "name": "Middle", "type": "release", "updated": 0}),
    )
    monkeypatch.setattr(FTBClient, "get_project", staticmethod(lambda *_args, **_kwargs: type("Project", (), {"versions": versions})()))

    result = FTBClient.list_versions(1, ("release",))

    assert [item.version_id for item in result] == [300, 200, 100]
