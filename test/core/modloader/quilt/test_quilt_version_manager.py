from pathlib import Path
from threading import Barrier, get_ident

import httpx
import pytest

from src.core.fs.paths import Paths
from src.core.modloader.quilt.quilt_meta_client import QuiltMetaClient
from src.core.modloader.quilt.quilt_version_manager import QuiltVersionManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.version import Version
from src.models.modloader.quilt_component import QuiltComponent
from src.models.modloader.quilt_install_metadata import QuiltInstallMetadata


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


def make_metadata() -> QuiltInstallMetadata:
    return QuiltInstallMetadata(
        game=QuiltComponent(uid="net.minecraft", version="1.20.1"),
        mappings=QuiltComponent(uid="org.quiltmc.hashed", version="1.20.1", maven="org.quiltmc:hashed:1.20.1"),
        loader=QuiltComponent(uid="org.quiltmc.quilt-loader", version="0.27.1", maven="org.quiltmc:quilt-loader:0.27.1"),
        main_class="org.quiltmc.loader.impl.launch.knot.KnotClient",
        libraries=(),
    )


def make_named_metadata() -> QuiltInstallMetadata:
    return QuiltInstallMetadata(
        game=QuiltComponent(uid="net.minecraft", version="26.2"),
        mappings=None,
        loader=QuiltComponent(uid="org.quiltmc.quilt-loader", version="0.20.0-beta.9", maven="org.quiltmc:quilt-loader:0.20.0-beta.9"),
        main_class="org.quiltmc.loader.impl.launch.knot.KnotClient",
        libraries=(),
    )


def make_profile():
    return {
        "id": "quilt-loader-0.27.1-1.20.1",
        "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient",
        "arguments": {"jvm": ["-Dquilt=true"], "game": []},
        "libraries": [
            {"name": "org.quiltmc:hashed:1.20.1", "url": "https://maven.quiltmc.org/repository/release/"},
            {"name": "org.quiltmc:quilt-loader:0.27.1", "url": "https://maven.quiltmc.org/repository/release/"},
        ],
    }


def test_merges_quilt_profile_with_component_metadata(tmp_path):
    base = make_base_version(tmp_path)
    quilt = make_profile()
    for index, library in enumerate(quilt["libraries"]):
        library["downloads"] = {"artifact": {"path": f"quilt/{index}.jar", "url": f"https://example/{index}.jar", "sha1": "d" * 40, "size": 1}}

    merged = QuiltVersionManager._merge_profiles(base.raw_json, quilt, make_metadata())

    assert merged["inheritsFrom"] == "1.20.1"
    assert merged["mainClass"].endswith("KnotClient")
    assert merged["arguments"]["jvm"] == ["-Dvanilla=true", "-Dquilt=true"]
    assert len(merged["libraries"]) == 3
    assert merged["quilt"]["schemaVersion"] == QuiltVersionManager.CACHE_SCHEMA_VERSION
    assert merged["quilt"]["mappingsVersion"] == "1.20.1"
    assert [component["uid"] for component in merged["quilt"]["components"]] == ["net.minecraft", "org.quiltmc.hashed", "org.quiltmc.quilt-loader"]


def test_merges_named_runtime_profile_without_mappings(tmp_path):
    base = make_base_version(tmp_path)
    base.id = "26.2"
    base.raw_json["id"] = "26.2"
    profile = {
        "id": "quilt-loader-0.20.0-beta.9-26.2",
        "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient",
        "arguments": {"jvm": ["-Dquilt=true"], "game": []},
        "libraries": [{"name": "org.quiltmc:quilt-loader:0.20.0-beta.9"}],
    }

    merged = QuiltVersionManager._merge_profiles(base.raw_json, profile, make_named_metadata())

    assert merged["quilt"]["mappingNamespace"] == "named"
    assert "mappingsVersion" not in merged["quilt"]
    assert [component["uid"] for component in merged["quilt"]["components"]] == ["net.minecraft", "org.quiltmc.quilt-loader"]


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

    monkeypatch.setattr(QuiltMetaClient, "get_install_metadata", get_metadata)
    monkeypatch.setattr(QuiltMetaClient, "get_profile", get_profile)
    monkeypatch.setattr(QuiltVersionManager, "_load_artifact_metadata", lambda artifact, force=False, reporter=None: ("e" * 40, 123))

    first = QuiltVersionManager.install(base, "0.27.1")
    second = QuiltVersionManager.install(base, "0.27.1")

    assert first.id == "quilt-loader-0.27.1-1.20.1"
    assert second.id == first.id
    assert calls == [("metadata", "1.20.1", "0.27.1", False), ("profile", "1.20.1", "0.27.1", False)]
    assert Paths.client(first) == Paths.CACHE_ROOT / "versions" / "1.20.1" / "1.20.1.jar"


def test_named_runtime_cache_does_not_require_mappings_component(tmp_path):
    base = make_base_version(tmp_path)
    base.id = "26.2"
    base.raw_json["id"] = "26.2"
    path = tmp_path / "quilt.json"
    profile = {
        "id": "quilt-loader-0.20.0-beta.9-26.2",
        "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient",
        "arguments": {"jvm": [], "game": []},
        "libraries": [{"name": "org.quiltmc:quilt-loader:0.20.0-beta.9"}],
    }
    merged = QuiltVersionManager._merge_profiles(base.raw_json, profile, make_named_metadata())
    path.write_text(__import__("json").dumps(merged), encoding="utf-8")

    cached = QuiltVersionManager._load_cached(path, base.raw_json, "26.2", "0.20.0-beta.9")

    assert cached is not None
    assert cached["quilt"]["mappingNamespace"] == "named"


def test_installs_named_runtime_without_mappings(tmp_path, monkeypatch):
    base = make_base_version(tmp_path)
    base.id = "26.2"
    base.raw_json["id"] = "26.2"
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(QuiltMetaClient, "get_install_metadata", lambda *args, **kwargs: make_named_metadata())
    monkeypatch.setattr(
        QuiltMetaClient,
        "get_profile",
        lambda *args, **kwargs: {
            "id": "quilt-loader-0.20.0-beta.9-26.2",
            "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient",
            "arguments": {"jvm": ["-Dquilt=true"], "game": []},
            "libraries": [{"name": "org.quiltmc:quilt-loader:0.20.0-beta.9", "url": "https://maven.quiltmc.org/repository/release/"}],
        },
    )
    monkeypatch.setattr(QuiltVersionManager, "_load_artifact_metadata", lambda artifact, force=False, reporter=None: ("e" * 40, 123))

    version = QuiltVersionManager.install(base, "0.20.0-beta.9")

    assert version.id == "quilt-loader-0.20.0-beta.9-26.2"
    assert version.raw_json["quilt"]["mappingNamespace"] == "named"
    assert "mappingsVersion" not in version.raw_json["quilt"]


def test_cache_is_invalidated_when_vanilla_metadata_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    base = make_base_version(tmp_path)
    changed = make_base_version(tmp_path, {"releaseTime": "later"})
    calls = []
    monkeypatch.setattr(QuiltMetaClient, "get_install_metadata", lambda *args, **kwargs: make_metadata())
    monkeypatch.setattr(QuiltMetaClient, "get_profile", lambda *args, **kwargs: calls.append(1) or make_profile())
    monkeypatch.setattr(QuiltVersionManager, "_load_artifact_metadata", lambda artifact, force=False, reporter=None: ("e" * 40, 123))

    QuiltVersionManager.install(base, "0.27.1")
    QuiltVersionManager.install(changed, "0.27.1")

    assert calls == [1, 1]


def test_repair_forces_metadata_refresh_and_library_fallback_refresh(tmp_path, monkeypatch):
    base = make_base_version(tmp_path)
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    calls = []
    monkeypatch.setattr(QuiltMetaClient, "get_install_metadata", lambda *args, **kwargs: calls.append(("metadata", kwargs["force_refresh"])) or make_metadata())
    monkeypatch.setattr(QuiltMetaClient, "get_profile", lambda *args, **kwargs: calls.append(("profile", kwargs["force_refresh"])) or make_profile())
    monkeypatch.setattr(QuiltVersionManager, "_load_artifact_metadata", lambda artifact, force=False, reporter=None: calls.append(("artifact", force)) or ("e" * 40, 123))

    QuiltVersionManager.repair(base, "0.27.1")

    assert ("metadata", True) in calls
    assert ("profile", True) in calls
    assert ("artifact", True) in calls


def test_missing_remote_sha1_downloads_and_hashes_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    artifact = type("Artifact", (), {"url": "https://example/quilt.jar", "path": Path("org/quiltmc/quilt.jar")})()

    class Response:
        text = "missing"
        headers = {}

        def raise_for_status(self):
            request = httpx.Request("GET", "https://example/quilt.jar.sha1")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("missing", request=request, response=response)

    class Client:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: Client())
    monkeypatch.setattr(HttpDownloader, "download_and_hash", lambda **kwargs: (kwargs["path"], "f" * 40, 456))

    assert QuiltVersionManager._load_artifact_metadata(artifact) == ("f" * 40, 456)


def test_quilt_library_replaces_same_maven_module_from_base_profile():
    base_library = {"name": "example:shared:1.0.0"}
    quilt_library = {"name": "example:shared:2.0.0"}
    assert QuiltVersionManager._merge_libraries([base_library], [quilt_library]) == [quilt_library]


def test_recommended_loader_prefers_newest_stable_version_regardless_of_api_order(monkeypatch):
    versions = [
        type("Loader", (), {"version": "0.24.0", "stable": True})(),
        type("Loader", (), {"version": "0.30.0-beta.2", "stable": False})(),
        type("Loader", (), {"version": "0.30.1", "stable": True})(),
        type("Loader", (), {"version": "0.20.0-beta.9", "stable": False})(),
    ]
    monkeypatch.setattr(QuiltMetaClient, "list_loader_versions", lambda game_version: versions)
    assert QuiltVersionManager.recommended_loader_version("26.2") == "0.30.1"


def test_recommended_loader_rejects_automatic_unstable_version(monkeypatch):
    versions = [type("Loader", (), {"version": "0.28.0-beta", "stable": False})()]
    monkeypatch.setattr(QuiltMetaClient, "list_loader_versions", lambda game_version: versions)

    with pytest.raises(RuntimeError, match="No stable Quilt Loader"):
        QuiltVersionManager.recommended_loader_version("1.20.1")


def test_rejects_quilt_profile_with_asm_too_old_for_java_25(tmp_path):
    base = make_base_version(tmp_path, {"id": "26.2", "javaVersion": {"majorVersion": 25}})
    base.id = "26.2"
    metadata = QuiltInstallMetadata(
        game=QuiltComponent(uid="net.minecraft", version="26.2"),
        mappings=None,
        loader=QuiltComponent(uid="org.quiltmc.quilt-loader", version="0.20.0-beta.9", maven="org.quiltmc:quilt-loader:0.20.0-beta.9"),
        main_class="org.quiltmc.loader.impl.launch.knot.KnotClient",
        libraries=({"name": "org.ow2.asm:asm:9.5"},),
    )

    with pytest.raises(RuntimeError, match=r"ASM 9\.5.*Java 25.*ASM 9\.8"):
        QuiltVersionManager._validate_bytecode_support(base, "0.20.0-beta.9", metadata, {})


def test_accepts_quilt_profile_with_java_25_capable_asm(tmp_path):
    base = make_base_version(tmp_path, {"id": "26.2", "javaVersion": {"majorVersion": 25}})
    base.id = "26.2"
    metadata = QuiltInstallMetadata(
        game=QuiltComponent(uid="net.minecraft", version="26.2"),
        mappings=None,
        loader=QuiltComponent(uid="org.quiltmc.quilt-loader", version="0.30.1", maven="org.quiltmc:quilt-loader:0.30.1"),
        main_class="org.quiltmc.loader.impl.launch.knot.KnotClient",
        libraries=({"name": "org.ow2.asm:asm:9.8"},),
    )

    QuiltVersionManager._validate_bytecode_support(base, "0.30.1", metadata, {})


def test_requires_asm_9_9_for_java_26(tmp_path):
    base = make_base_version(tmp_path, {"id": "future", "javaVersion": {"majorVersion": 26}})
    base.id = "future"
    metadata = QuiltInstallMetadata(
        game=QuiltComponent(uid="net.minecraft", version="future"),
        mappings=None,
        loader=QuiltComponent(uid="org.quiltmc.quilt-loader", version="0.30.0", maven="org.quiltmc:quilt-loader:0.30.0"),
        main_class="org.quiltmc.loader.impl.launch.knot.KnotClient",
        libraries=({"name": "org.ow2.asm:asm:9.8"},),
    )

    with pytest.raises(RuntimeError, match=r"Java 26.*ASM 9\.9"):
        QuiltVersionManager._validate_bytecode_support(base, "0.30.0", metadata, {})


def test_missing_library_metadata_is_resolved_concurrently(monkeypatch):
    profile = {
        "libraries": [
            {"name": "example:first:1.0", "url": "https://example.invalid/"},
            {"name": "example:second:1.0", "url": "https://example.invalid/"},
        ]
    }
    barrier = Barrier(2)
    worker_threads: set[int] = set()

    def load_metadata(artifact, force=False, reporter=None):
        worker_threads.add(get_ident())
        barrier.wait(timeout=1)
        return "e" * 40, 123

    monkeypatch.setattr(QuiltVersionManager, "_load_artifact_metadata", load_metadata)

    normalized = QuiltVersionManager._normalize_profile_libraries(profile)

    assert len(worker_threads) == 2
    assert [item["name"] for item in normalized["libraries"]] == ["example:first:1.0", "example:second:1.0"]
