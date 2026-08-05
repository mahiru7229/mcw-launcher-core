from pathlib import Path

import httpx
import pytest

from src.core.fs.paths import Paths
from src.core.modloader.fabric.fabric_meta_client import FabricMetaClient
from src.core.modloader.fabric.fabric_version_manager import FabricVersionManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.version import Version
from src.models.modloader.fabric_component import FabricComponent
from src.models.modloader.fabric_install_metadata import FabricInstallMetadata


def make_base_version(tmp_path: Path, extra: dict | None = None) -> Version:
    raw = {
        "id": "1.20.1",
        "type": "release",
        "arguments": {"jvm": ["-Dvanilla=true"], "game": ["--username", "${auth_player_name}"]},
        "assetIndex": {"id": "5", "url": "https://example/assets", "sha1": "a" * 40, "size": 1, "totalSize": 1},
        "assets": "5",
        "downloads": {"client": {"url": "https://example/client.jar", "sha1": "b" * 40, "size": 1}},
        "javaVersion": {"majorVersion": 17},
        "libraries": [{"name": "vanilla:library:1", "downloads": {"artifact": {"path": "vanilla/library/1/library-1.jar", "url": "https://example/library.jar", "sha1": "c" * 40, "size": 1}}}],
        "mainClass": "net.minecraft.client.main.Main",
    }
    raw.update(extra or {})
    path = tmp_path / "1.20.1.json"
    path.write_text("{}", encoding="utf-8")
    return Version(id="1.20.1", path=path, libraries=raw["libraries"], downloads=raw["downloads"], asset_index=raw["assetIndex"], assets="5", main_class=raw["mainClass"], java_version=raw["javaVersion"], raw_json=raw, type="release", arguments=raw["arguments"], minecraft_arguments=None)


def make_metadata() -> FabricInstallMetadata:
    return FabricInstallMetadata(
        game=FabricComponent(uid="net.minecraft", version="1.20.1"),
        intermediary=FabricComponent(uid="net.fabricmc.intermediary", version="1.20.1", maven="net.fabricmc:intermediary:1.20.1"),
        loader=FabricComponent(uid="net.fabricmc.fabric-loader", version="0.19.3", maven="net.fabricmc:fabric-loader:0.19.3"),
        main_class="net.fabricmc.loader.impl.launch.knot.KnotClient",
        libraries=(),
    )


def make_profile():
    return {
        "id": "fabric-loader-0.19.3-1.20.1",
        "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
        "arguments": {"jvm": ["-Dfabric=true"], "game": []},
        "libraries": [{"name": "net.fabricmc:fabric-loader:0.19.3", "url": "https://maven.fabricmc.net/"}],
    }


def test_merges_fabric_profile_with_component_metadata(tmp_path):
    base = make_base_version(tmp_path)
    fabric = make_profile()
    fabric["libraries"][0]["downloads"] = {"artifact": {"path": "net/fabricmc/fabric-loader/0.19.3/fabric-loader-0.19.3.jar", "url": "https://example/fabric.jar", "sha1": "d" * 40, "size": 1}}

    merged = FabricVersionManager._merge_profiles(base.raw_json, fabric, make_metadata())

    assert merged["inheritsFrom"] == "1.20.1"
    assert merged["mainClass"].endswith("KnotClient")
    assert merged["arguments"]["jvm"] == ["-Dvanilla=true", "-Dfabric=true"]
    assert len(merged["libraries"]) == 2
    assert merged["fabric"]["schemaVersion"] == FabricVersionManager.CACHE_SCHEMA_VERSION
    assert merged["fabric"]["intermediaryVersion"] == "1.20.1"
    assert [component["uid"] for component in merged["fabric"]["components"]] == ["net.minecraft", "net.fabricmc.intermediary", "net.fabricmc.fabric-loader"]


def test_installs_and_reuses_cached_profile(tmp_path, monkeypatch):
    base = make_base_version(tmp_path)
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    calls = []

    def get_metadata(game_version, loader_version, force_refresh=False):
        calls.append(("metadata", game_version, loader_version, force_refresh))
        return make_metadata()

    def get_profile(game_version, loader_version, force_refresh=False):
        calls.append(("profile", game_version, loader_version, force_refresh))
        return make_profile()

    monkeypatch.setattr(FabricMetaClient, "get_install_metadata", get_metadata)
    monkeypatch.setattr(FabricMetaClient, "get_profile", get_profile)
    monkeypatch.setattr(FabricVersionManager, "_load_artifact_metadata", lambda artifact, force=False: ("e" * 40, 123))

    first = FabricVersionManager.install(base, "0.19.3")
    second = FabricVersionManager.install(base, "0.19.3")

    assert first.id == "fabric-loader-0.19.3-1.20.1"
    assert second.id == first.id
    assert calls == [
        ("metadata", "1.20.1", "0.19.3", False),
        ("profile", "1.20.1", "0.19.3", False),
    ]
    assert Paths.client(first) == Paths.CACHE_ROOT / "versions" / "1.20.1" / "1.20.1.jar"


def test_cache_is_invalidated_when_vanilla_metadata_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    base = make_base_version(tmp_path)
    changed = make_base_version(tmp_path, {"releaseTime": "later"})
    calls = []
    monkeypatch.setattr(FabricMetaClient, "get_install_metadata", lambda *args, **kwargs: make_metadata())
    monkeypatch.setattr(FabricMetaClient, "get_profile", lambda *args, **kwargs: calls.append(1) or make_profile())
    monkeypatch.setattr(FabricVersionManager, "_load_artifact_metadata", lambda artifact, force=False: ("e" * 40, 123))

    FabricVersionManager.install(base, "0.19.3")
    FabricVersionManager.install(changed, "0.19.3")

    assert calls == [1, 1]


def test_repair_forces_metadata_refresh_and_library_fallback_refresh(tmp_path, monkeypatch):
    base = make_base_version(tmp_path)
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    calls = []
    monkeypatch.setattr(FabricMetaClient, "get_install_metadata", lambda *args, **kwargs: calls.append(("metadata", kwargs["force_refresh"])) or make_metadata())
    monkeypatch.setattr(FabricMetaClient, "get_profile", lambda *args, **kwargs: calls.append(("profile", kwargs["force_refresh"])) or make_profile())
    monkeypatch.setattr(FabricVersionManager, "_load_artifact_metadata", lambda artifact, force=False: calls.append(("artifact", force)) or ("e" * 40, 123))

    FabricVersionManager.repair(base, "0.19.3")

    assert ("metadata", True) in calls
    assert ("profile", True) in calls
    assert ("artifact", True) in calls


def test_missing_remote_sha1_downloads_and_hashes_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    artifact = type("Artifact", (), {"url": "https://example/fabric.jar", "path": Path("net/fabric/fabric.jar")})()

    class Response:
        text = "missing"
        headers = {}

        def raise_for_status(self):
            request = httpx.Request("GET", "https://example/fabric.jar.sha1")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("missing", request=request, response=response)

    class Client:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: Client())
    monkeypatch.setattr(HttpDownloader, "download_and_hash", lambda **kwargs: (kwargs["path"], "f" * 40, 456))

    assert FabricVersionManager._load_artifact_metadata(artifact) == ("f" * 40, 456)


def test_fabric_library_replaces_same_maven_module_from_base_profile():
    base_library = {"name": "example:shared:1.0.0"}
    fabric_library = {"name": "example:shared:2.0.0"}
    assert FabricVersionManager._merge_libraries([base_library], [fabric_library]) == [fabric_library]


def test_library_key_keeps_classifiers_separate():
    regular = FabricVersionManager._library_key("example:shared:1.0.0")
    native = FabricVersionManager._library_key("example:shared:1.0.0:natives-windows")
    assert regular != native


def test_recommended_loader_prefers_first_stable_version(monkeypatch):
    versions = [
        type("Loader", (), {"version": "0.20.0-beta", "stable": False})(),
        type("Loader", (), {"version": "0.19.3", "stable": True})(),
        type("Loader", (), {"version": "0.18.6", "stable": True})(),
    ]
    monkeypatch.setattr(FabricMetaClient, "list_loader_versions", lambda game_version: versions)
    assert FabricVersionManager.recommended_loader_version("1.21.1") == "0.19.3"


def test_recommended_loader_rejects_automatic_unstable_version(monkeypatch):
    versions = [
        type("Loader", (), {"version": "0.20.0-beta", "stable": False})(),
        type("Loader", (), {"version": "0.19.4-beta", "stable": False})(),
    ]
    monkeypatch.setattr(FabricMetaClient, "list_loader_versions", lambda game_version: versions)

    with pytest.raises(RuntimeError, match="No stable Fabric Loader"):
        FabricVersionManager.recommended_loader_version("1.21.1")
