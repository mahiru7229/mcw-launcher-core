import json

from src.core.modrinth.modrinth_client import ModrinthClient


def test_search_builds_loader_facets_but_keeps_game_version_advisory(monkeypatch):
    captured = {}

    def fake_get_json(path, params=None, ttl=0, force_refresh=False, **_kwargs):
        captured.update(path=path, params=params, ttl=ttl)
        return {
            "hits": [{
                "project_id": "abc123",
                "slug": "example",
                "title": "Example Mod",
                "description": "Example",
                "project_type": "mod",
                "author": "Author",
                "downloads": 42,
                "categories": ["fabric"],
                "client_side": "required",
            }],
            "total_hits": 1,
            "offset": 0,
            "limit": 25,
        }

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    result = ModrinthClient.search_projects("mod", "example", game_version="1.20.1", loader="fabric")

    facets = json.loads(captured["params"]["facets"])
    assert ["project_type:mod"] in facets
    assert ["categories:fabric"] in facets
    assert ["versions:1.20.1"] not in facets
    assert result.projects[0].title == "Example Mod"
    assert result.projects[0].client_side == "required"


def test_versions_are_sorted_by_publish_date_across_channels(monkeypatch):
    monkeypatch.setattr(ModrinthClient, "_get_json", lambda *args, **kwargs: [
        {
            "id": "beta",
            "project_id": "project",
            "name": "Beta",
            "version_number": "2.0-beta",
            "version_type": "beta",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "featured": False,
            "date_published": "2026-07-12T00:00:00Z",
            "files": [{"url": "https://cdn.modrinth.com/beta.jar", "filename": "beta.jar", "hashes": {"sha1": "a", "sha512": "b"}, "size": 1, "primary": True}],
        },
        {
            "id": "release",
            "project_id": "project",
            "name": "Release",
            "version_number": "1.0",
            "version_type": "release",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "featured": True,
            "date_published": "2026-07-10T00:00:00Z",
            "files": [{"url": "https://cdn.modrinth.com/release.jar", "filename": "release.jar", "hashes": {"sha1": "c", "sha512": "d"}, "size": 1, "primary": True}],
        },
    ])

    versions = ModrinthClient.list_project_versions("project", loader="fabric", game_version="1.20.1")

    assert [version.version_id for version in versions] == ["beta", "release"]
    assert versions[0].primary_file(".jar").filename == "beta.jar"


def test_versions_keep_nearby_patch_metadata_and_rank_likely_matches(monkeypatch):
    captured = {}

    def version(version_id: str, game_versions: list[str], published: str):
        return {
            "id": version_id,
            "project_id": "project",
            "name": version_id,
            "version_number": version_id,
            "version_type": "release",
            "game_versions": game_versions,
            "loaders": ["fabric"],
            "date_published": published,
            "files": [{
                "url": f"https://cdn.modrinth.com/{version_id}.jar",
                "filename": f"{version_id}.jar",
                "hashes": {"sha1": "a", "sha512": "b"},
                "size": 1,
                "primary": True,
            }],
        }

    def fake_get_json(path, params=None, **_kwargs):
        captured["params"] = params
        return [
            version("other", ["1.21.1"], "2026-07-28T00:00:00Z"),
            version("nearby", ["1.20.4"], "2026-07-27T00:00:00Z"),
            version("unknown", [], "2026-07-26T00:00:00Z"),
            version("exact", ["1.20.1"], "2026-07-25T00:00:00Z"),
        ]

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    versions = ModrinthClient.list_project_versions(
        "project",
        loader="fabric",
        game_version="1.20.1",
    )

    assert "game_versions" not in captured["params"]
    assert [version.version_id for version in versions] == ["exact", "nearby", "unknown", "other"]


def test_search_ranks_exact_and_nearby_patch_projects_without_hiding_others(monkeypatch):
    def fake_get_json(*_args, **_kwargs):
        return {
            "hits": [
                {"project_id": "other", "title": "Other", "project_type": "mod", "versions": ["1.21.1"]},
                {"project_id": "nearby", "title": "Nearby", "project_type": "mod", "versions": ["1.20.4"]},
                {"project_id": "exact", "title": "Exact", "project_type": "mod", "versions": ["1.20.1"]},
            ],
            "total_hits": 3,
            "offset": 0,
            "limit": 25,
        }

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    result = ModrinthClient.search_projects(
        "mod",
        "example",
        game_version="1.20.1",
        loader="fabric",
    )

    assert [project.project_id for project in result.projects] == ["exact", "nearby", "other"]


def test_user_agent_identifies_launcher():
    assert "mcw-launcher" in ModrinthClient.USER_AGENT
    assert "mahiru7229" in ModrinthClient.USER_AGENT


def test_project_versions_filter_release_channels(monkeypatch):
    def version(version_id: str, version_type: str):
        return {
            "id": version_id,
            "project_id": "project",
            "name": version_id,
            "version_number": version_id,
            "version_type": version_type,
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "featured": False,
            "date_published": f"2026-07-{10 + len(version_id):02d}T00:00:00Z",
            "files": [{"url": f"https://cdn.modrinth.com/{version_id}.jar", "filename": f"{version_id}.jar", "hashes": {"sha1": "a", "sha512": "b"}, "size": 1, "primary": True}],
        }

    monkeypatch.setattr(ModrinthClient, "_get_json", lambda *args, **kwargs: [version("release", "release"), version("beta", "beta"), version("alpha", "alpha")])

    releases = ModrinthClient.list_project_versions("project", version_types=("release",))
    beta_enabled = ModrinthClient.list_project_versions("project", version_types=("release", "beta"))
    all_channels = ModrinthClient.list_project_versions("project", version_types=("release", "beta", "alpha"))

    assert {item.version_type for item in releases} == {"release"}
    assert {item.version_type for item in beta_enabled} == {"release", "beta"}
    assert {item.version_type for item in all_channels} == {"release", "beta", "alpha"}
    assert ModrinthClient.normalize_version_types(()) == ("release",)


def test_search_builds_forge_facets(monkeypatch):
    calls = []

    def fake_get_json(path, params=None, ttl=0, force_refresh=False, **_kwargs):
        calls.append({"path": path, "params": params, "force_refresh": force_refresh})
        return {"hits": [], "total_hits": 0, "offset": 0, "limit": 25}

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    ModrinthClient.search_projects("modpack", "forge", loader="forge")

    facets = json.loads(calls[0]["params"]["facets"])
    assert ["project_type:modpack"] in facets
    assert ["categories:forge"] in facets


def test_modpack_search_retries_without_loader_facet_when_filtered_page_is_empty(monkeypatch):
    calls = []

    def fake_get_json(path, params=None, ttl=0, force_refresh=False, **_kwargs):
        facets = json.loads(params["facets"])
        calls.append((facets, force_refresh))
        if ["categories:fabric"] in facets:
            return {"hits": [], "total_hits": 0, "offset": 0, "limit": 25}
        return {
            "hits": [
                {
                    "project_id": "fabric-pack",
                    "slug": "fabric-pack",
                    "title": "Fabric Pack",
                    "description": "Compatible",
                    "project_type": "modpack",
                    "author": "Author",
                    "downloads": 10,
                    "categories": ["fabric", "optimization"],
                },
                {
                    "project_id": "neoforge-pack",
                    "slug": "neoforge-pack",
                    "title": "NeoForge Pack",
                    "description": "Wrong loader",
                    "project_type": "modpack",
                    "author": "Author",
                    "downloads": 5,
                    "categories": ["neoforge"],
                },
            ],
            "total_hits": 2,
            "offset": 0,
            "limit": 25,
        }

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    result = ModrinthClient.search_projects("modpack", "opti", loader="fabric")

    assert [project.project_id for project in result.projects] == ["fabric-pack"]
    assert result.total_hits == 1
    assert len(calls) == 2
    assert ["categories:fabric"] in calls[0][0]
    assert ["categories:fabric"] not in calls[1][0]
    assert calls[1][1] is True


def test_modpack_search_keeps_primary_loader_filtered_result_without_fallback(monkeypatch):
    calls = []

    def fake_get_json(path, params=None, ttl=0, force_refresh=False, **_kwargs):
        calls.append(json.loads(params["facets"]))
        return {
            "hits": [{
                "project_id": "forge-pack",
                "slug": "forge-pack",
                "title": "Forge Pack",
                "description": "Compatible",
                "project_type": "modpack",
                "author": "Author",
                "downloads": 10,
                "categories": ["forge"],
            }],
            "total_hits": 1,
            "offset": 0,
            "limit": 25,
        }

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    result = ModrinthClient.search_projects("modpack", "opti", loader="forge")

    assert [project.project_id for project in result.projects] == ["forge-pack"]
    assert len(calls) == 1


def test_default_modpack_catalog_does_not_silently_accept_two_empty_responses(monkeypatch):
    monkeypatch.setattr(
        ModrinthClient,
        "_get_json",
        lambda *args, **kwargs: {"hits": [], "total_hits": 0, "offset": 0, "limit": 25},
    )

    import pytest

    with pytest.raises(RuntimeError, match="returned no modpacks"):
        ModrinthClient.search_projects("modpack", "", loader="fabric")


def test_empty_default_search_cache_is_not_a_usable_network_fallback():
    payload = {"hits": [], "total_hits": 0, "offset": 0, "limit": 25}

    assert not ModrinthClient._cached_payload_is_usable("/search", {"facets": "[]"}, payload)
    assert not ModrinthClient._cached_payload_is_usable("/search", {"query": "no-such-pack"}, payload)


def test_search_network_error_does_not_return_empty_default_cache(monkeypatch, tmp_path):
    import httpx
    import pytest

    cache_path = tmp_path / "search.json"
    cache_path.write_text(
        json.dumps(
            {
                "schemaVersion": ModrinthClient.CACHE_SCHEMA,
                "fetchedAt": 0,
                "payload": {"hits": [], "total_hits": 0, "offset": 0, "limit": 25},
            }
        ),
        encoding="utf-8",
    )

    class FailingClient:
        def get(self, *args, **kwargs):
            raise httpx.ConnectError("offline", request=httpx.Request("GET", "https://api.modrinth.com/v2/search"))

    from src.core.fs.paths import Paths
    from src.core.network.httpx_downloader import HttpDownloader

    monkeypatch.setattr(Paths, "modrinth_api_cache", staticmethod(lambda _key: cache_path))
    monkeypatch.setattr(HttpDownloader, "get_client", classmethod(lambda cls: FailingClient()))

    with pytest.raises(RuntimeError, match="Unable to contact Modrinth"):
        ModrinthClient._get_json(
            "/search",
            params={"facets": '[["project_type:modpack"]]', "index": "downloads", "offset": 0, "limit": 25},
            ttl=600,
            force_refresh=True,
        )


def test_quilt_search_uses_quilt_and_fabric_facets(monkeypatch):
    captured = {}

    def get_json(path, params=None, **kwargs):
        captured.update(params or {})
        return {"hits": [], "total_hits": 0, "offset": 0, "limit": 25}

    monkeypatch.setattr(ModrinthClient, "_get_json", get_json)

    ModrinthClient.search_projects("mod", "example", loader="quilt")

    facets = json.loads(captured["facets"])
    assert ["categories:quilt", "categories:fabric"] in facets


def test_quilt_version_query_preserves_exact_loader_priority(monkeypatch):
    payload = [
        {
            "id": "fabric-version",
            "project_id": "project",
            "name": "Fabric fallback",
            "version_number": "1.0.0",
            "version_type": "release",
            "game_versions": ["1.20.1"],
            "loaders": ["fabric"],
            "files": [],
            "date_published": "2026-01-02T00:00:00Z",
        },
        {
            "id": "quilt-version",
            "project_id": "project",
            "name": "Quilt exact",
            "version_number": "0.9.0",
            "version_type": "release",
            "game_versions": ["1.20.1"],
            "loaders": ["quilt"],
            "files": [],
            "date_published": "2026-01-01T00:00:00Z",
        },
    ]
    captured = {}

    def get_json(path, params=None, **kwargs):
        captured.update(params or {})
        return payload

    monkeypatch.setattr(ModrinthClient, "_get_json", get_json)

    versions = ModrinthClient.list_project_versions("project", loader="quilt", game_version="1.20.1")

    assert json.loads(captured["loaders"]) == ["quilt", "fabric"]
    assert [version.version_id for version in versions] == ["quilt-version", "fabric-version"]


def test_project_parser_keeps_rich_detail_metadata() -> None:
    project = ModrinthClient._parse_project({
        "id": "sodium",
        "slug": "sodium",
        "title": "Sodium",
        "description": "Renderer",
        "body": "# Sodium\nFast rendering.",
        "project_type": "mod",
        "author": "CaffeineMC",
        "downloads": 1234,
        "followers": 321,
        "icon_url": "https://cdn.modrinth.com/icon.png",
        "categories": ["optimization", "fabric"],
        "loaders": ["fabric", "quilt"],
        "versions": ["1.21.1"],
        "client_side": "required",
        "server_side": "unsupported",
        "published": "2024-01-01T00:00:00Z",
        "updated": "2026-08-01T00:00:00Z",
        "source_url": "https://github.com/example/sodium",
        "issues_url": "https://github.com/example/sodium/issues",
        "wiki_url": "https://example.invalid/wiki",
        "discord_url": "https://example.invalid/discord",
        "license": {"id": "LGPL-3.0", "name": "LGPL", "url": "https://example.invalid/license"},
        "gallery": [{"url": "https://cdn.modrinth.com/gallery.png"}],
    })

    assert project.body.startswith("# Sodium")
    assert project.project_url == "https://modrinth.com/mod/sodium"
    assert project.license_id == "LGPL-3.0"
    assert project.gallery_urls == ("https://cdn.modrinth.com/gallery.png",)
    assert project.loaders == ("fabric", "quilt")
    assert project.followers == 321


def test_search_supports_resource_pack_and_shader_project_types(monkeypatch):
    calls = []

    def fake_get_json(path, params=None, **_kwargs):
        calls.append(json.loads(params["facets"]))
        return {"hits": [], "total_hits": 0, "offset": 0, "limit": 25}

    monkeypatch.setattr(ModrinthClient, "_get_json", fake_get_json)

    ModrinthClient.search_projects("resourcepack", "faithful")
    ModrinthClient.search_projects("shader", "complementary")

    assert ["project_type:resourcepack"] in calls[0]
    assert ["project_type:shader"] in calls[1]
