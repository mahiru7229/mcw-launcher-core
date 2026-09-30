from pathlib import Path
from threading import Thread
from time import sleep

import httpx
import pytest

from src.config import CURSEFORGE_USER_AGENT, VERSION_ID
from src.core.config.curseforge_config_manager import CurseForgeConfigManager
from src.core.curseforge.curseforge_cache import CurseForgeCache
from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.network.httpx_downloader import HttpDownloader
from src.models.curseforge.file import CurseForgeFile


def configure_gateway(monkeypatch, tmp_path: Path, client: httpx.Client, token: str = "") -> None:
    monkeypatch.setattr(CurseForgeConfigManager, "gateway_urls", staticmethod(lambda: ("https://gateway.example/api/curseforge",)))
    monkeypatch.setattr(CurseForgeConfigManager, "client_token", staticmethod(lambda: token))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: client))
    monkeypatch.setattr(CurseForgeCache, "root", staticmethod(lambda: tmp_path))
    CurseForgeClient._inflight.clear()


def search_payload() -> dict:
    return {
        "data": [{
            "id": 101,
            "name": "Example",
            "slug": "example",
            "summary": "Forge mod",
            "downloadCount": 10,
            "authors": [{"name": "Mahiru"}],
            "logo": {"thumbnailUrl": "https://example/icon.png"},
            "links": {"websiteUrl": "https://www.curseforge.com/minecraft/mc-mods/example"},
            "classId": 6,
            "dateModified": "2026-01-01T00:00:00Z",
        }],
        "pagination": {"index": 0, "pageSize": 25, "totalCount": 1},
    }


def test_search_projects_uses_gateway_filters_and_safe_headers(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, request=request, json=search_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client, token="public-client-token")

    result = CurseForgeClient.search_projects("mod", query="example", game_version="1.20.1", loader="forge", force_refresh=True)

    request = captured["request"]
    assert request.url.path == "/api/curseforge/search"
    assert request.headers["user-agent"] == CURSEFORGE_USER_AGENT
    assert request.headers["x-mcw-version"] == VERSION_ID
    assert request.headers["authorization"] == "Bearer public-client-token"
    assert "x-api-key" not in request.headers
    assert request.url.params["query"] == "example"
    assert request.url.params["classId"] == "6"
    assert "loader" not in request.url.params
    assert "gameVersion" not in request.url.params
    assert result.projects[0].project_id == 101
    assert result.projects[0].authors == ("Mahiru",)
    assert result.projects[0].project_url.endswith("/example")
    assert result.cache_info.from_cache is False
    client.close()


def test_fresh_search_cache_avoids_a_second_gateway_request(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, json=search_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    first = CurseForgeClient.search_projects("mod", query="example", game_version="1.20.1", loader="forge")
    second = CurseForgeClient.search_projects("mod", query="example", game_version="1.20.1", loader="forge")

    assert calls == 1
    assert first.cache_info.from_cache is False
    assert second.cache_info.from_cache is True
    client.close()


def test_identical_concurrent_requests_are_coalesced(monkeypatch, tmp_path: Path) -> None:
    calls = 0
    results = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        sleep(0.05)
        return httpx.Response(200, request=request, json=search_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    def run() -> None:
        results.append(CurseForgeClient.search_projects("mod", query="example", game_version="1.20.1", loader="forge", force_refresh=True))

    threads = [Thread(target=run), Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == 1
    assert len(results) == 2
    client.close()


def test_parse_file_includes_sha1_dependencies_loader_and_distribution_state() -> None:
    file = CurseForgeClient._parse_file({
        "id": 22,
        "modId": 11,
        "displayName": "Example 1.0",
        "fileName": "example.jar",
        "releaseType": 2,
        "fileDate": "2026-01-01T00:00:00Z",
        "fileLength": 123,
        "downloadUrl": "https://example/example.jar",
        "hashes": [{"algo": 1, "value": "a" * 40}],
        "gameVersions": ["1.20.1", "Forge", "Java 17", "Client"],
        "dependencies": [{"modId": 99, "relationType": 3}],
        "isAvailable": False,
    })

    assert file.release_type == "beta"
    assert file.sha1 == "a" * 40
    assert file.dependencies[0].required is True
    assert file.is_available is False
    assert file.game_versions == ("1.20.1",)
    assert file.loaders == ("forge",)


def test_credentials_unavailable_is_a_permanent_gateway_error() -> None:
    error = RuntimeError("The CurseForge gateway credentials are unavailable.")
    setattr(error, "gateway_error_code", "CURSEFORGE_CREDENTIALS_UNAVAILABLE")
    setattr(error, "gateway_status", 503)

    assert CurseForgeClient.is_permanent_error(error) is True


def test_gateway_failure_returns_stale_cache_with_error_state(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, request=request, json=search_payload())
        return httpx.Response(
            503,
            request=request,
            json={"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "CurseForge is unavailable."}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    first = CurseForgeClient.search_projects("mod", query="example", game_version="1.20.1", loader="forge")
    fallback = CurseForgeClient.search_projects(
        "mod",
        query="example",
        game_version="1.20.1",
        loader="forge",
        force_refresh=True,
    )

    assert calls == 2
    assert first.cache_info.from_cache is False
    assert fallback.cache_info.from_cache is True
    assert fallback.projects[0].project_id == 101
    assert CurseForgeClient.cache_status().last_error == "CurseForge is unavailable."
    client.close()


def test_catalog_search_filters_projects_by_latest_file_loader(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "data": [
            {
                "id": 101,
                "name": "Forge only",
                "slug": "forge-only",
                "latestFilesIndexes": [
                    {"gameVersion": "1.20.1", "fileId": 1, "modLoader": 1},
                ],
            },
            {
                "id": 102,
                "name": "Fabric only",
                "slug": "fabric-only",
                "latestFilesIndexes": [
                    {"gameVersion": "1.20.1", "fileId": 2, "modLoader": 4},
                ],
            },
        ],
        "pagination": {"index": 0, "pageSize": 25, "totalCount": 2},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        # Loader metadata is advisory, so search does not let the upstream API
        # remove potentially universal projects. Likely matches are ranked first.
        assert "loader" not in request.url.params
        return httpx.Response(200, request=request, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    result = CurseForgeClient.search_projects("mod", query="hunter", loader="fabric", force_refresh=True)

    assert [project.project_id for project in result.projects] == [102, 101]
    assert result.projects[0].loaders == ("fabric",)
    assert result.projects[0].game_versions == ("1.20.1",)
    client.close()


def test_catalog_file_list_ranks_advisory_loader_and_game_version_metadata(monkeypatch, tmp_path: Path) -> None:
    captured = {}
    payload = {
        "data": [
            {"id": 1, "modId": 1515343, "displayName": "Fabric-labelled", "fileName": "universal.jar", "releaseType": 1, "fileDate": "2026-07-22T00:00:00Z", "gameVersions": ["1.20.1", "Fabric"]},
            {"id": 2, "modId": 1515343, "displayName": "Forge", "fileName": "forge.jar", "releaseType": 1, "fileDate": "2026-07-20T00:00:00Z", "gameVersions": ["1.20.1", "Forge"]},
            {"id": 3, "modId": 1515343, "displayName": "Universal", "fileName": "both.jar", "releaseType": 1, "fileDate": "2026-07-21T00:00:00Z", "gameVersions": ["1.20.1", "Fabric", "Forge"]},
            {"id": 4, "modId": 1515343, "displayName": "Nearby patch", "fileName": "nearby.jar", "releaseType": 1, "fileDate": "2026-07-24T00:00:00Z", "gameVersions": ["1.20.4", "Forge"]},
            {"id": 5, "modId": 1515343, "displayName": "Other release", "fileName": "other.jar", "releaseType": 1, "fileDate": "2026-07-26T00:00:00Z", "gameVersions": ["1.21.1", "Forge"]},
            {"id": 6, "modId": 1515343, "displayName": "Unknown game version", "fileName": "unknown.jar", "releaseType": 1, "fileDate": "2026-07-25T00:00:00Z", "gameVersions": ["Forge"]},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, request=request, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    result = CurseForgeClient.list_files_result(1515343, game_version="1.20.1", loader="forge", force_refresh=True)

    assert [file.file_id for file in result.files] == [2, 4, 6, 5, 3, 1]
    assert "loader" not in captured["request"].url.params
    assert "gameVersion" not in captured["request"].url.params
    assert CurseForgeClient.loader_compatibility(result.files[-1], "forge") == "unverified"
    client.close()


def test_catalog_search_keeps_and_ranks_nearby_patch_projects(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "data": [
            {
                "id": 1,
                "name": "Other release",
                "slug": "other",
                "latestFilesIndexes": [{"gameVersion": "1.21.1", "fileId": 1, "modLoader": 4}],
            },
            {
                "id": 2,
                "name": "Nearby patch",
                "slug": "nearby",
                "latestFilesIndexes": [{"gameVersion": "1.20.4", "fileId": 2, "modLoader": 4}],
            },
            {
                "id": 3,
                "name": "Exact",
                "slug": "exact",
                "latestFilesIndexes": [{"gameVersion": "1.20.1", "fileId": 3, "modLoader": 4}],
            },
        ],
        "pagination": {"index": 0, "pageSize": 25, "totalCount": 3},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "gameVersion" not in request.url.params
        return httpx.Response(200, request=request, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    result = CurseForgeClient.search_projects(
        "mod",
        query="example",
        game_version="1.20.1",
        loader="fabric",
        force_refresh=True,
    )

    assert [project.project_id for project in result.projects] == [3, 2, 1]
    client.close()


def test_request_fails_over_to_next_gateway(monkeypatch, tmp_path: Path) -> None:
    requested_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "primary.example":
            return httpx.Response(503, request=request, json={"error": {"message": "Primary unavailable."}})
        return httpx.Response(200, request=request, json=search_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        CurseForgeConfigManager,
        "gateway_urls",
        staticmethod(lambda: (
            "https://primary.example/api/curseforge",
            "https://secondary.example/api/curseforge",
        )),
    )
    monkeypatch.setattr(CurseForgeConfigManager, "client_token", staticmethod(lambda: ""))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: client))
    monkeypatch.setattr(CurseForgeCache, "root", staticmethod(lambda: tmp_path))
    CurseForgeClient._inflight.clear()

    result = CurseForgeClient.search_projects("mod", query="example", force_refresh=True)

    assert requested_hosts == ["primary.example", "secondary.example"]
    assert result.projects[0].project_id == 101
    client.close()


def test_non_transient_gateway_error_does_not_fail_over(monkeypatch, tmp_path: Path) -> None:
    requested_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        return httpx.Response(403, request=request, json={"error": {"message": "Forbidden."}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        CurseForgeConfigManager,
        "gateway_urls",
        staticmethod(lambda: (
            "https://primary.example/api/curseforge",
            "https://secondary.example/api/curseforge",
        )),
    )
    monkeypatch.setattr(CurseForgeConfigManager, "client_token", staticmethod(lambda: ""))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: client))
    monkeypatch.setattr(CurseForgeCache, "root", staticmethod(lambda: tmp_path))
    CurseForgeClient._inflight.clear()

    with pytest.raises(RuntimeError, match="Forbidden"):
        CurseForgeClient._request_json(
            "GET",
            "/search",
            params={"query": "example"},
            force_refresh=True,
            allow_stale_on_error=False,
            namespace="failover-test",
        )

    assert requested_hosts == ["primary.example"]
    client.close()


def test_parse_file_recognizes_declared_fabric_and_forge_as_universal() -> None:
    file = CurseForgeClient._parse_file({
        "id": 33,
        "modId": 11,
        "fileName": "universal.jar",
        "gameVersions": ["1.20.1", "Fabric", "Forge"],
    })

    assert file.loaders == ("fabric", "forge")
    assert CurseForgeClient.loader_compatibility(file, "fabric") == "universal"
    assert CurseForgeClient.loader_compatibility(file, "forge") == "universal"


def test_modpack_fallback_project_url_uses_modpacks_path() -> None:
    project = CurseForgeClient._parse_project({
        "id": 77,
        "name": "Example Pack",
        "slug": "example-pack",
        "classId": CurseForgeClient.CLASS_MODPACKS,
    })

    assert project.project_url == "https://www.curseforge.com/minecraft/modpacks/example-pack"


def test_project_url_rejects_untrusted_scheme_and_uses_safe_fallback() -> None:
    project = CurseForgeClient._parse_project({
        "id": 88,
        "name": "Safe Project",
        "slug": "safe-project",
        "classId": CurseForgeClient.CLASS_MODS,
        "links": {"websiteUrl": "file:///C:/Windows/System32/calc.exe"},
    })

    assert project.project_url == "https://www.curseforge.com/minecraft/mc-mods/safe-project"


def test_file_list_keeps_unknown_game_version_metadata_for_runtime_validation(monkeypatch, tmp_path: Path) -> None:
    payload = {
        "data": [{
            "id": 9,
            "modId": 7,
            "displayName": "Universal metadata-light build",
            "fileName": "universal.jar",
            "releaseType": 1,
            "fileDate": "2026-07-25T00:00:00Z",
            "gameVersions": ["Fabric"],
        }]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    result = CurseForgeClient.list_files_result(7, game_version="1.20.1", loader="forge", force_refresh=True)

    assert [file.file_id for file in result.files] == [9]
    assert result.files[0].game_versions == ()
    assert CurseForgeClient.loader_compatibility(result.files[0], "forge") == "unverified"
    client.close()


def test_gateway_v011_manual_download_error_is_permanent():
    error = RuntimeError("This CurseForge file must be downloaded manually because third-party distribution is unavailable.")
    setattr(error, "gateway_error_code", "manual_download_required")
    setattr(error, "gateway_status", 409)

    assert CurseForgeClient.is_permanent_error(error) is True


def test_gateway_v011_credentials_rejected_is_permanent():
    error = RuntimeError("CurseForge rejected the gateway credentials.")
    setattr(error, "gateway_error_code", "gateway_credentials_rejected")
    setattr(error, "gateway_status", 503)

    assert CurseForgeClient.is_permanent_error(error) is True


def test_quilt_loader_compatibility_accepts_fabric_as_fallback() -> None:
    fabric_file = CurseForgeClient._parse_file({
        "id": 1,
        "modId": 2,
        "fileName": "fabric.jar",
        "gameVersions": ["1.20.1", "Fabric"],
        "hashes": [],
        "dependencies": [],
    })
    quilt_file = CurseForgeClient._parse_file({
        "id": 2,
        "modId": 2,
        "fileName": "quilt.jar",
        "gameVersions": ["1.20.1", "Quilt"],
        "hashes": [],
        "dependencies": [],
    })

    assert CurseForgeClient.loader_compatibility(fabric_file, "quilt") == "compatible"
    assert CurseForgeClient._loader_rank(quilt_file.loaders, "quilt") < CurseForgeClient._loader_rank(fabric_file.loaders, "quilt")


def test_project_parser_keeps_rich_detail_metadata() -> None:
    project = CurseForgeClient._parse_project({
        "id": 42,
        "name": "Example Project",
        "slug": "example-project",
        "summary": "A useful project",
        "downloadCount": 9001,
        "authors": [{"name": "Mahiru"}],
        "logo": {"thumbnailUrl": "https://media.forgecdn.net/icon.png"},
        "classId": CurseForgeClient.CLASS_MODS,
        "dateModified": "2026-08-01T00:00:00Z",
        "dateCreated": "2025-01-01T00:00:00Z",
        "dateReleased": "2026-07-31T00:00:00Z",
        "status": 4,
        "isFeatured": True,
        "links": {
            "websiteUrl": "https://www.curseforge.com/minecraft/mc-mods/example-project",
            "sourceUrl": "https://github.com/example/project",
            "issuesUrl": "https://github.com/example/project/issues",
            "wikiUrl": "https://example.invalid/wiki",
        },
        "categories": [{"name": "Technology"}, {"name": "Magic"}],
        "screenshots": [{"url": "https://media.forgecdn.net/screenshot.png"}],
        "latestFilesIndexes": [
            {"gameVersion": "1.21.1", "fileId": 1, "modLoader": 4},
            {"gameVersion": "1.21.1", "fileId": 2, "modLoader": 6},
        ],
    })

    assert project.authors == ("Mahiru",)
    assert project.categories == ("Technology", "Magic")
    assert project.screenshot_urls == ("https://media.forgecdn.net/screenshot.png",)
    assert project.game_versions == ("1.21.1",)
    assert project.loaders == ("fabric", "neoforge")
    assert project.source_url == "https://github.com/example/project"
    assert project.is_featured is True


def test_search_supports_resource_pack_and_shader_class_ids(monkeypatch, tmp_path: Path) -> None:
    class_ids = []

    def handler(request: httpx.Request) -> httpx.Response:
        class_ids.append(request.url.params["classId"])
        return httpx.Response(200, request=request, json={"data": [], "pagination": {"index": 0, "pageSize": 25, "totalCount": 0}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    configure_gateway(monkeypatch, tmp_path, client)

    CurseForgeClient.search_projects("resourcepack", query="faithful", game_version="1.21.1", loader="fabric", force_refresh=True)
    CurseForgeClient.search_projects("shader", query="complementary", game_version="1.21.1", loader="forge", force_refresh=True)

    assert class_ids == ["12", "6552"]
    client.close()


def test_fabric_forge_universal_metadata_is_not_neoforge_compatible() -> None:
    file = CurseForgeClient._parse_file({
        "id": 34,
        "modId": 11,
        "fileName": "fabric-forge.jar",
        "gameVersions": ["1.20.1", "Fabric", "Forge"],
    })

    assert CurseForgeClient.loader_compatibility(file, "neoforge") == "unverified"


def test_latest_compatible_file_skips_foreign_loader_candidate(monkeypatch) -> None:
    fabric = CurseForgeFile(file_id=8443275, project_id=306612, display_name="Fabric API", file_name="fabric-api.jar", release_type="release", file_date="2026-08-01T00:00:00Z", file_length=10, download_url="", sha1="a" * 40, game_versions=("1.20.1",), dependencies=(), loaders=("fabric",))
    forge = CurseForgeFile(file_id=9000000, project_id=306612, display_name="Forge-compatible", file_name="forge-compatible.jar", release_type="release", file_date="2026-07-01T00:00:00Z", file_length=10, download_url="", sha1="b" * 40, game_versions=("1.20.1",), dependencies=(), loaders=("forge",))
    monkeypatch.setattr(CurseForgeClient, "list_files", staticmethod(lambda *_args, **_kwargs: [fabric, forge]))

    selected = CurseForgeClient.latest_compatible_file(306612, "1.20.1", loader="forge")

    assert selected.file_id == 9000000


def test_latest_compatible_file_rejects_wrong_minecraft_version(monkeypatch) -> None:
    nearby = CurseForgeFile(file_id=1, project_id=2, display_name="Nearby", file_name="nearby.jar", release_type="release", file_date="", file_length=10, download_url="", sha1="a" * 40, game_versions=("1.20.4",), dependencies=(), loaders=("forge",))
    monkeypatch.setattr(CurseForgeClient, "list_files", staticmethod(lambda *_args, **_kwargs: [nearby]))

    with pytest.raises(RuntimeError, match="No compatible Forge file for Minecraft 1.20.1"):
        CurseForgeClient.latest_compatible_file(2, "1.20.1", loader="forge")
