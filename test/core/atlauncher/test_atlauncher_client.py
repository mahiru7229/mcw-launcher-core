from pathlib import Path

import httpx

from src.config import ATLAUNCHER_USER_AGENT
from src.core.atlauncher.atlauncher_cache import ATLauncherCache
from src.core.atlauncher.atlauncher_client import ATLauncherClient
from src.core.network.httpx_downloader import HttpDownloader


def configure_client(monkeypatch, tmp_path: Path, handler) -> httpx.Client:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: client))
    monkeypatch.setattr(ATLauncherCache, "root", staticmethod(lambda: tmp_path))
    return client


def project_payload() -> dict:
    return {
        "id": 25,
        "position": 2,
        "name": "Example Pack",
        "safeName": "ExamplePack",
        "type": "public",
        "description": "A test ATLauncher pack. More details follow.",
        "supportURL": "https://support.example/pack",
        "websiteURL": "https://example.invalid/pack",
        "versions": [
            {
                "id": 101,
                "version": "2.0.0",
                "minecraftVersion": "1.20.1",
                "recommended": True,
                "published": 1760000000,
                "changelog": "Stable",
            },
            {
                "id": 100,
                "version": "2.0.0-beta",
                "minecraftVersion": "1.20.1",
                "recommended": False,
                "published": 1750000000,
                "changelog": "Beta",
            },
        ],
    }


def version_manifest() -> dict:
    return {
        "minecraft": "1.20.1",
        "loader": {"type": "forge", "metadata": {"version": "47.4.0"}},
        "configs": {"filesize": 120, "sha1": "c" * 40},
        "memory": {"minimum": 4096, "recommended": 6144},
        "mods": [
            {
                "name": "Required Mod",
                "version": "1.0.0",
                "file": "required.jar",
                "url": "https://cdn.example/required.jar",
                "download": "direct",
                "type": "mods",
                "md5": "a" * 32,
                "client": True,
            },
            {
                "name": "Server Hosted Mod",
                "version": "1.0.0",
                "file": "server.jar",
                "url": "packs/ExamplePack/server.jar",
                "download": "server",
                "type": "mods",
                "md5": "b" * 32,
                "client": True,
            },
        ],
    }


def test_search_uses_public_v2_graphql_contract(monkeypatch, tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request, json={"data": {"packs": [{
            "id": 25,
            "position": 2,
            "name": "Example Pack",
            "safeName": "ExamplePack",
            "latestVersion": {
                "id": 101,
                "version": "2.0.0",
                "minecraftVersion": "1.20.1",
                "changelog": "Stable",
                "isRecommended": True,
                "canUpdate": False,
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-02T00:00:00Z",
                "publishedAt": "2026-01-03T00:00:00Z",
            },
        }]}})

    client = configure_client(monkeypatch, tmp_path, handler)
    result = ATLauncherClient.search_projects(force_refresh=True)

    assert requests[0].url == httpx.URL(ATLauncherClient.GRAPHQL_URL)
    assert requests[0].headers["user-agent"] == ATLAUNCHER_USER_AGENT
    body = requests[0].read().decode("utf-8")
    assert "isDevelopment" not in body
    assert "rawJson" not in body
    assert result.projects[0].safe_name == "ExamplePack"
    assert result.projects[0].versions[0].release_type == "release"
    client.close()


def test_project_uses_public_v1_details_and_parses_versions(monkeypatch, tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, request=request, json=project_payload())

    client = configure_client(monkeypatch, tmp_path, handler)
    project = ATLauncherClient.get_project("ExamplePack", force_refresh=True)
    versions = ATLauncherClient.list_versions("ExamplePack", ("release",), force_refresh=False)

    assert paths == ["/v1/pack/ExamplePack"]
    assert project.description.startswith("A test")
    assert project.support_url == "https://support.example/pack"
    assert [version.version for version in versions] == ["2.0.0"]
    assert project.icon_url.endswith("launcher/images/examplepack.png")
    client.close()


def test_version_uses_configs_json_and_builds_deferred_files(monkeypatch, tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/Configs.json"):
            return httpx.Response(200, request=request, json=version_manifest())
        if request.url.path.endswith("/v1/pack/ExamplePack"):
            return httpx.Response(200, request=request, json=project_payload())
        return httpx.Response(404, request=request)

    client = configure_client(monkeypatch, tmp_path, handler)
    version = ATLauncherClient.get_version("ExamplePack", "2.0.0", force_refresh=True)

    assert paths[0].endswith("/packs/ExamplePack/versions/2.0.0/Configs.json")
    assert version.minecraft_version == "1.20.1"
    assert version.loader == "forge"
    assert version.loader_version == "47.4.0"
    assert version.recommended_memory_mb == 6144
    assert version.config_bundle is not None
    assert version.config_bundle.url.endswith("/packs/ExamplePack/versions/2.0.0/Configs.zip")
    assert version.files[0].urls == ("https://cdn.example/required.jar",)
    assert version.files[1].urls == ("https://download.nodecdn.net/containers/atl/packs/ExamplePack/server.jar",)
    assert not version.unsupported_actions
    client.close()


def test_graphql_failure_falls_back_to_v1_pack_list(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, request=request, json={"errors": [{"message": "schema changed"}]})
        if request.url.path.endswith("/v1/packs/full/public"):
            return httpx.Response(200, request=request, json=[project_payload()])
        return httpx.Response(404, request=request)

    client = configure_client(monkeypatch, tmp_path, handler)
    result = ATLauncherClient.search_projects("Example", force_refresh=True)

    assert result.projects[0].name == "Example Pack"
    assert calls[:2] == [("POST", "/v2/graphql"), ("GET", "/v1/packs/full/public")]
    client.close()
