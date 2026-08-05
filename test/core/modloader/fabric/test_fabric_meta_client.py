from pathlib import Path

import httpx
import pytest

from src.core.fs.paths import Paths
from src.core.modloader.fabric.fabric_meta_client import FabricMetaClient
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


def loader_entry(loader_version="0.19.3", stable=True, game_version="1.21.5"):
    return {
        "loader": {
            "version": loader_version,
            "stable": stable,
            "maven": f"net.fabricmc:fabric-loader:{loader_version}",
        },
        "intermediary": {
            "version": game_version,
            "stable": True,
            "maven": f"net.fabricmc:intermediary:{game_version}",
        },
    }


def install_payload(loader_version="0.19.3", game_version="1.21.5"):
    return {
        **loader_entry(loader_version, True, game_version),
        "launcherMeta": {
            "mainClass": {"client": "net.fabricmc.loader.impl.launch.knot.KnotClient"},
            "libraries": {
                "common": [{"name": "org.ow2.asm:asm:9.7", "url": "https://maven.fabricmc.net/"}],
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
    url = FabricMetaClient.BASE_URL + "/versions/loader/1.21.5"
    client = FakeClient({url: [loader_entry(), loader_entry("0.19.2", False)]})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    first = FabricMetaClient.list_loader_versions("1.21.5")
    second = FabricMetaClient.list_loader_versions("1.21.5")

    assert [version.version for version in first] == ["0.19.3", "0.19.2"]
    assert first[0].stable is True
    assert first[0].intermediary_version == "1.21.5"
    assert first[0].loader_maven == "net.fabricmc:fabric-loader:0.19.3"
    assert second == first
    assert client.urls == [url]


def test_url_encodes_game_and_loader_versions(monkeypatch):
    game_version = "1.14 Pre-Release 5"
    loader_version = "0.4.2+build.132"
    encoded_url = FabricMetaClient.BASE_URL + "/versions/loader/1.14%20Pre-Release%205/0.4.2%2Bbuild.132"
    client = FakeClient({encoded_url: install_payload(loader_version, game_version)})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    metadata = FabricMetaClient.get_install_metadata(game_version, loader_version)

    assert metadata.game.version == game_version
    assert metadata.loader.version == loader_version
    assert client.urls == [encoded_url]


def test_uses_stale_catalog_when_refresh_fails(monkeypatch):
    url = FabricMetaClient.BASE_URL + "/versions/loader/1.21.5"
    working = FakeClient({url: [loader_entry()]})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: working)
    assert FabricMetaClient.list_loader_versions("1.21.5")

    request = httpx.Request("GET", url)
    failing = FakeClient({url: httpx.ConnectError("offline", request=request)})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: failing)

    versions = FabricMetaClient.list_loader_versions("1.21.5", force_refresh=True)

    assert [version.version for version in versions] == ["0.19.3"]


def test_loads_install_components(monkeypatch):
    url = FabricMetaClient.BASE_URL + "/versions/loader/1.21.5/0.19.3"
    client = FakeClient({url: install_payload()})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    metadata = FabricMetaClient.get_install_metadata("1.21.5", "0.19.3")

    assert metadata.game.uid == "net.minecraft"
    assert metadata.intermediary.uid == "net.fabricmc.intermediary"
    assert metadata.loader.uid == "net.fabricmc.fabric-loader"
    assert metadata.main_class.endswith("KnotClient")
    assert metadata.libraries[0]["name"] == "org.ow2.asm:asm:9.7"


def test_loads_profile_and_reuses_cache(monkeypatch):
    url = FabricMetaClient.BASE_URL + "/versions/loader/1.21.5/0.19.3/profile/json"
    profile = {"id": "fabric-loader", "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient"}
    client = FakeClient({url: profile})
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)

    assert FabricMetaClient.get_profile("1.21.5", "0.19.3") == profile
    assert FabricMetaClient.get_profile("1.21.5", "0.19.3") == profile
    assert client.urls == [url]
