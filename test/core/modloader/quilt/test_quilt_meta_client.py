from pathlib import Path

import httpx
import pytest

from src.core.fs.paths import Paths
from src.core.modloader.quilt.quilt_meta_client import QuiltMetaClient
from src.core.network.httpx_downloader import HttpDownloader


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def loader_entry(loader_version="0.27.1", stable=True, game_version="1.20.1", mapping_kind="hashed"):
    return {
        "loader": {
            "version": loader_version,
            "stable": stable,
            "maven": f"org.quiltmc:quilt-loader:{loader_version}",
        },
        mapping_kind: {
            "version": game_version,
            "stable": True,
            "maven": f"org.quiltmc:{mapping_kind}:{game_version}",
        },
    }


def install_payload(loader_version="0.27.1", game_version="1.20.1", mapping_kind="hashed"):
    return {
        **loader_entry(loader_version, True, game_version, mapping_kind),
        "launcherMeta": {
            "mainClass": {"client": "org.quiltmc.loader.impl.launch.knot.KnotClient"},
            "libraries": {
                "common": [{"name": "org.ow2.asm:asm:9.7", "url": "https://maven.quiltmc.org/repository/release/"}],
                "client": [],
            },
        },
    }


def install_payload_without_mappings(loader_version="0.20.0-beta.9"):
    return {
        "loader": {
            "version": loader_version,
            "stable": False,
            "maven": f"org.quiltmc:quilt-loader:{loader_version}",
        },
        "launcherMeta": {
            "mainClass": {"client": "org.quiltmc.loader.impl.launch.knot.KnotClient"},
            "libraries": {
                "common": [{"name": "org.ow2.asm:asm:9.9", "url": "https://maven.quiltmc.org/repository/release/"}],
                "client": [],
            },
        },
    }


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    HttpDownloader.close_client()
    yield
    HttpDownloader.close_client()


def test_lists_loader_versions_and_reuses_fresh_cache(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/1.20.1"
    client = FakeClient({url: [loader_entry(), loader_entry("0.27.0-beta", False)]})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    first = QuiltMetaClient.list_loader_versions("1.20.1")
    second = QuiltMetaClient.list_loader_versions("1.20.1")

    assert [version.version for version in first] == ["0.27.1", "0.27.0-beta"]
    assert first[0].stable is True
    assert first[0].mappings_version == "1.20.1"
    assert first[0].loader_maven == "org.quiltmc:quilt-loader:0.27.1"
    assert second == first
    assert client.urls == [url]


def test_accepts_intermediary_component_for_legacy_meta(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/1.20.1"
    client = FakeClient({url: [loader_entry(mapping_kind="intermediary")]})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    versions = QuiltMetaClient.list_loader_versions("1.20.1")

    assert versions[0].mappings_maven == "org.quiltmc:intermediary:1.20.1"


def test_url_encodes_game_and_loader_versions(monkeypatch):
    game_version = "1.14 Pre-Release 5"
    loader_version = "0.27.1+build.2"
    encoded_url = QuiltMetaClient.BASE_URL + "/versions/loader/1.14%20Pre-Release%205/0.27.1%2Bbuild.2"
    client = FakeClient({encoded_url: install_payload(loader_version, game_version)})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    metadata = QuiltMetaClient.get_install_metadata(game_version, loader_version)

    assert metadata.game.version == game_version
    assert metadata.loader.version == loader_version
    assert client.urls == [encoded_url]


def test_uses_stale_catalog_when_refresh_fails(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/1.20.1"
    working = FakeClient({url: [loader_entry()]})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: working)
    assert QuiltMetaClient.list_loader_versions("1.20.1")

    request = httpx.Request("GET", url)
    failing = FakeClient({url: httpx.ConnectError("offline", request=request)})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: failing)

    versions = QuiltMetaClient.list_loader_versions("1.20.1", force_refresh=True)

    assert [version.version for version in versions] == ["0.27.1"]


def test_loads_install_components(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/1.20.1/0.27.1"
    client = FakeClient({url: install_payload()})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    metadata = QuiltMetaClient.get_install_metadata("1.20.1", "0.27.1")

    assert metadata.game.uid == "net.minecraft"
    assert metadata.mappings.uid == "org.quiltmc.hashed"
    assert metadata.loader.uid == "org.quiltmc.quilt-loader"
    assert metadata.main_class.endswith("KnotClient")
    assert metadata.libraries[0]["name"] == "org.ow2.asm:asm:9.7"


def test_accepts_named_runtime_metadata_without_mappings(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/26.2/0.20.0-beta.9"
    client = FakeClient({url: install_payload_without_mappings()})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    metadata = QuiltMetaClient.get_install_metadata("26.2", "0.20.0-beta.9")

    assert metadata.game.version == "26.2"
    assert metadata.mappings is None
    assert metadata.loader.version == "0.20.0-beta.9"
    assert metadata.main_class.endswith("KnotClient")
    assert metadata.libraries[0]["name"] == "org.ow2.asm:asm:9.9"


def test_loads_profile_and_reuses_cache(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/1.20.1/0.27.1/profile/json"
    profile = {"id": "quilt-loader", "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient"}
    client = FakeClient({url: profile})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    assert QuiltMetaClient.get_profile("1.20.1", "0.27.1") == profile
    assert QuiltMetaClient.get_profile("1.20.1", "0.27.1") == profile
    assert client.urls == [url]


def test_sorts_loader_versions_newest_first_and_infers_stable_when_flag_is_missing(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/26.2"
    payload = [
        {"loader": {"version": "0.20.0-beta.9", "maven": "org.quiltmc:quilt-loader:0.20.0-beta.9"}},
        {"loader": {"version": "0.24.0", "maven": "org.quiltmc:quilt-loader:0.24.0"}},
        {"loader": {"version": "0.30.1", "maven": "org.quiltmc:quilt-loader:0.30.1"}},
        {"loader": {"version": "0.30.0-beta.2", "maven": "org.quiltmc:quilt-loader:0.30.0-beta.2"}},
    ]
    client = FakeClient({url: payload})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    versions = QuiltMetaClient.list_loader_versions("26.2")

    assert [version.version for version in versions] == ["0.30.1", "0.30.0-beta.2", "0.24.0", "0.20.0-beta.9"]
    assert [version.stable for version in versions] == [True, False, True, False]


def test_explicit_stability_flag_wins_over_version_name(monkeypatch):
    url = QuiltMetaClient.BASE_URL + "/versions/loader/26.2"
    payload = [{"loader": {"version": "0.30.1", "stable": False, "maven": "org.quiltmc:quilt-loader:0.30.1"}}]
    client = FakeClient({url: payload})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    versions = QuiltMetaClient.list_loader_versions("26.2")

    assert versions[0].stable is False
