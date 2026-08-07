from pathlib import Path

from src.core.fs.paths import Paths
from src.core.modloader.forge.forge_version_manager import ForgeVersionManager
from src.models.minecraft.version import Version


def make_version(tmp_path: Path) -> Version:
    raw = {
        "id": "1.20.1",
        "arguments": {"game": ["--demo"], "jvm": ["-Dbase=true"]},
        "libraries": [{"name": "com.example:base:1.0"}],
        "downloads": {"client": {"url": "https://example/client.jar", "sha1": "a" * 40, "size": 1}},
        "assetIndex": {"id": "1.20", "url": "https://example/assets.json", "sha1": "b" * 40, "size": 1},
        "assets": "1.20",
        "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {"majorVersion": 17},
    }
    return Version(
        id="1.20.1",
        arguments=raw["arguments"],
        minecraft_arguments=None,
        libraries=raw["libraries"],
        downloads=raw["downloads"],
        asset_index=raw["assetIndex"],
        assets=raw["assets"],
        main_class=raw["mainClass"],
        java_version=raw["javaVersion"],
        raw_json=raw,
        path=tmp_path / "1.20.1.json",
        type="release",
    )


def test_merge_profiles_keeps_base_and_adds_forge() -> None:
    base = make_version(Path(".")).raw_json
    profile = {
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "arguments": {"game": ["--fml.forgeVersion", "47.3.0"], "jvm": ["-Dforge=true"]},
        "libraries": [{"name": "net.minecraftforge:forge:1.20.1-47.3.0"}],
    }

    merged = ForgeVersionManager._merge_profiles(base, profile, "1.20.1", "47.3.0")

    assert merged["mainClass"] == profile["mainClass"]
    assert merged["inheritsFrom"] == "1.20.1"
    assert len(merged["libraries"]) == 2
    assert merged["arguments"]["game"][-2:] == ["--fml.forgeVersion", "47.3.0"]
    assert merged["forge"]["loaderVersion"] == "47.3.0"


def test_prepare_staging_writes_launcher_layout(monkeypatch, tmp_path: Path) -> None:
    version = make_version(tmp_path)
    cached_client = tmp_path / "cache" / "1.20.1.jar"
    cached_client.parent.mkdir()
    cached_client.write_bytes(b"client")
    monkeypatch.setattr(Paths, "client", staticmethod(lambda current: cached_client))

    staging = tmp_path / "staging"
    staging.mkdir()
    ForgeVersionManager._prepare_staging(version, staging)

    assert (staging / "launcher_profiles.json").is_file()
    assert (staging / "versions" / "1.20.1" / "1.20.1.json").is_file()
    assert (staging / "versions" / "1.20.1" / "1.20.1.jar").read_bytes() == b"client"


def test_run_installer_imports_legacy_without_starting_java(monkeypatch, tmp_path: Path) -> None:
    import hashlib
    import json
    import zipfile

    installer = tmp_path / "forge-installer.jar"
    library = b"legacy-forge"
    coordinate = "net.minecraftforge:forge:1.8.9-11.15.1.2318-1.8.9:universal"
    profile_id = "1.8.9-Forge11.15.1.2318-1.8.9"
    profile = {
        "install": {"target": profile_id, "path": coordinate},
        "versionInfo": {
            "id": profile_id,
            "mainClass": "net.minecraft.launchwrapper.Launch",
            "libraries": [{"name": coordinate, "checksums": [hashlib.sha1(library, usedforsecurity=False).hexdigest()]}],
        },
    }
    with zipfile.ZipFile(installer, "w") as archive:
        archive.writestr("install_profile.json", json.dumps(profile))
        archive.writestr("forge-1.8.9-11.15.1.2318-1.8.9-universal.jar", library)

    forge_root = tmp_path / "forge-root"
    monkeypatch.setattr(Paths, "forge_root", staticmethod(lambda: forge_root))
    monkeypatch.setattr("src.core.modloader.forge.forge_version_manager.ModLoaderJavaRunner.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Java must not run for a legacy profile")))

    ForgeVersionManager._run_installer(make_version(tmp_path), "11.15.1.2318-1.8.9", installer, tmp_path / "staging", None)

    assert (tmp_path / "staging" / "versions" / profile_id / f"{profile_id}.json").is_file()
    assert "Legacy Forge installer imported" in (forge_root / "logs" / "forge-1.20.1-11.15.1.2318-1.8.9.log").read_text(encoding="utf-8")


def test_normalize_legacy_library_builds_download_metadata(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    sha1 = "a" * 40
    profile = {
        "libraries": [
            {
                "name": "com.example:legacy:1.0",
                "url": "https://repo.example/maven/",
                "checksums": [sha1],
            }
        ]
    }

    normalized = ForgeVersionManager._normalize_libraries(profile)
    artifact = normalized["libraries"][0]["downloads"]["artifact"]

    assert artifact["path"] == "com/example/legacy/1.0/legacy-1.0.jar"
    assert artifact["url"] == "https://repo.example/maven/com/example/legacy/1.0/legacy-1.0.jar"
    assert artifact["sha1"] == sha1
    assert artifact["size"] == 0


def test_normalize_hashless_legacy_library_downloads_and_records_sha1(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    calls = []

    def fake_download_and_hash(**kwargs):
        calls.append(kwargs)
        target = kwargs["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"launchwrapper")
        return target, "b" * 40, len(b"launchwrapper")

    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(fake_download_and_hash),
    )
    profile = {
        "libraries": [
            {
                "name": "net.minecraft:launchwrapper:1.8",
                "checksums": ["d41d8cd98f00b204e9800998ecf8427e"],
            }
        ]
    }

    normalized = ForgeVersionManager._normalize_libraries(profile)
    artifact = normalized["libraries"][0]["downloads"]["artifact"]

    assert calls[0]["url"] == "https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar"
    assert artifact == {
        "path": "net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar",
        "url": "https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar",
        "sha1": "b" * 40,
        "size": len(b"launchwrapper"),
    }


def test_normalize_legacy_native_only_library_builds_windows_classifier(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    calls = []

    def fake_download_and_hash(**kwargs):
        calls.append(kwargs)
        target = kwargs["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"native-library")
        return target, "c" * 40, len(b"native-library")

    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(fake_download_and_hash),
    )
    profile = {
        "libraries": [
            {
                "name": "org.lwjgl.lwjgl:lwjgl-platform:2.9.0",
                "natives": {"windows": "natives-windows"},
                "extract": {"exclude": ["META-INF/"]},
            }
        ]
    }

    normalized = ForgeVersionManager._normalize_libraries(profile)
    library = normalized["libraries"][0]
    classifiers = library["downloads"]["classifiers"]

    assert "artifact" not in library["downloads"]
    assert calls[0]["url"] == "https://libraries.minecraft.net/org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar"
    assert classifiers["natives-windows"] == {
        "path": "org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar",
        "url": "https://libraries.minecraft.net/org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar",
        "sha1": "c" * 40,
        "size": len(b"native-library"),
    }


def test_normalize_legacy_platform_infers_windows_native_when_mapping_is_missing(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))

    def fake_download_and_hash(**kwargs):
        target = kwargs["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"native-library")
        return target, "f" * 40, len(b"native-library")

    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(fake_download_and_hash),
    )
    profile = {"libraries": [{"name": "net.java.jinput:jinput-platform:2.0.5"}]}

    normalized = ForgeVersionManager._normalize_libraries(profile)
    library = normalized["libraries"][0]

    assert library["natives"] == {"windows": "natives-windows"}
    assert "artifact" not in library["downloads"]
    assert library["downloads"]["classifiers"]["natives-windows"]["path"] == "net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-windows.jar"


def test_normalize_jna_platform_as_regular_artifact_without_native_classifier(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    calls = []

    def fake_download_and_hash(**kwargs):
        calls.append(kwargs)
        target = kwargs["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jna-platform")
        return target, "9" * 40, len(b"jna-platform")

    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(fake_download_and_hash),
    )

    normalized = ForgeVersionManager._normalize_libraries({"libraries": [{"name": "net.java.dev.jna:jna-platform:5.10.0"}]})
    library = normalized["libraries"][0]

    assert "natives" not in library
    assert "classifiers" not in library["downloads"]
    assert library["downloads"]["artifact"]["path"] == "net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar"
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar")


def test_normalize_removes_spurious_jna_native_metadata_from_v4_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(lambda **kwargs: (_ for _ in ()).throw(AssertionError("The valid JNA artifact must be reused"))),
    )
    artifact = {
        "path": "net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar",
        "url": "https://libraries.minecraft.net/net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar",
        "sha1": "8" * 40,
        "size": 1,
    }
    profile = {
        "libraries": [{
            "name": "net.java.dev.jna:jna-platform:5.10.0",
            "natives": {"windows": "natives-windows"},
            "downloads": {"artifact": artifact},
        }]
    }

    normalized = ForgeVersionManager._normalize_libraries(profile)
    library = normalized["libraries"][0]

    assert "natives" not in library
    assert library["downloads"] == {"artifact": artifact}


def test_polluted_jna_platform_cache_is_repaired_without_forge_installer(monkeypatch, tmp_path: Path) -> None:
    import json

    base = make_version(tmp_path)
    cache = tmp_path / "forge-1.20.1-47.3.0.json"
    artifact = {
        "path": "net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar",
        "url": "https://libraries.minecraft.net/net/java/dev/jna/jna-platform/5.10.0/jna-platform-5.10.0.jar",
        "sha1": "8" * 40,
        "size": 1,
    }
    cached_profile = json.loads(json.dumps(base.raw_json))
    cached_profile.update({
        "id": "forge-1.20.1-47.3.0",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "arguments": {"game": ["--fml.forgeVersion", "47.3.0"], "jvm": []},
        "libraries": [
            {"name": "net.minecraftforge:forge:1.20.1-47.3.0", "downloads": {"artifact": {"path": "net/minecraftforge/forge/1.20.1-47.3.0/forge-1.20.1-47.3.0.jar", "url": "https://maven.minecraftforge.net/forge.jar", "sha1": "7" * 40, "size": 1}}},
            {"name": "net.java.dev.jna:jna-platform:5.10.0", "natives": {"windows": "natives-windows"}, "downloads": {"artifact": artifact}},
        ],
        "forge": {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.3.0"},
    })
    cache.write_text(json.dumps(cached_profile), encoding="utf-8")

    monkeypatch.setattr(Paths, "forge_version_json", staticmethod(lambda *_args: cache))
    monkeypatch.setattr(ForgeVersionManager, "_download_installer", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Forge installer must not run"))))
    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(lambda **kwargs: (_ for _ in ()).throw(AssertionError("No library download should be needed"))),
    )

    version = ForgeVersionManager.install(base, "47.3.0")
    repaired = json.loads(cache.read_text(encoding="utf-8"))
    jna = next(item for item in repaired["libraries"] if item["name"].startswith("net.java.dev.jna:jna-platform:"))

    assert version.id == "forge-1.20.1-47.3.0"
    assert "natives" not in jna
    assert jna["downloads"] == {"artifact": artifact}


def test_normalize_skips_osx_only_nightly_native_on_windows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_os",
        staticmethod(lambda: "windows"),
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_arch",
        staticmethod(lambda: "x64"),
    )
    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(lambda **kwargs: (_ for _ in ()).throw(AssertionError("A disallowed OS library must not be downloaded"))),
    )
    library = {
        "name": "org.lwjgl.lwjgl:lwjgl-platform:2.9.1-nightly-20130708-debug3",
        "natives": {"linux": "natives-linux", "osx": "natives-osx", "windows": "natives-windows"},
        "rules": [{"action": "allow", "os": {"name": "osx", "version": "^10\\.5\\.\\d$"}}],
        "extract": {"exclude": ["META-INF/"]},
    }

    normalized = ForgeVersionManager._normalize_libraries({"libraries": [library]})

    assert normalized["libraries"] == [library]
    assert "downloads" not in normalized["libraries"][0]


def test_windows_native_cache_ignores_osx_only_nightly_library(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_os",
        staticmethod(lambda: "windows"),
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_arch",
        staticmethod(lambda: "x64"),
    )
    cache = tmp_path / "forge.json"
    cache.write_text(
        '{"id":"forge-1.6.4-9.11.1.1345","mainClass":"net.minecraft.launchwrapper.Launch","libraries":['
        '{"name":"net.minecraft:launchwrapper:1.8","downloads":{"artifact":{"path":"net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","url":"https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","sha1":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":100}}},'
        '{"name":"org.lwjgl.lwjgl:lwjgl-platform:2.9.0","natives":{"windows":"natives-windows"},"downloads":{"classifiers":{"natives-windows":{"path":"org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar","url":"https://libraries.minecraft.net/org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar","sha1":"cccccccccccccccccccccccccccccccccccccccc","size":609967}}}},'
        '{"name":"org.lwjgl.lwjgl:lwjgl-platform:2.9.1-nightly-20130708-debug3","natives":{"linux":"natives-linux","osx":"natives-osx","windows":"natives-windows"},"rules":[{"action":"allow","os":{"name":"osx","version":"^10\\\\.5\\\\.\\\\d$"}}]}],"forge":{"schemaVersion":1,"gameVersion":"1.6.4","loaderVersion":"9.11.1.1345"}}',
        encoding="utf-8",
    )

    assert ForgeVersionManager._load_cached(cache, "1.6.4", "9.11.1.1345") is not None


def test_normalize_legacy_native_library_preserves_existing_artifact(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    calls = []

    def fake_download_and_hash(**kwargs):
        calls.append(kwargs)
        target = kwargs["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"native")
        return target, "d" * 40, len(b"native")

    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.HttpDownloader.download_and_hash",
        staticmethod(fake_download_and_hash),
    )
    artifact = {
        "path": "com/example/hybrid/1.0/hybrid-1.0.jar",
        "url": "https://repo.example/com/example/hybrid/1.0/hybrid-1.0.jar",
        "sha1": "e" * 40,
        "size": 10,
    }
    profile = {
        "libraries": [
            {
                "name": "com.example:hybrid:1.0",
                "url": "https://repo.example/",
                "natives": {"windows": "natives-windows-${arch}"},
                "downloads": {"artifact": artifact},
            }
        ]
    }

    normalized = ForgeVersionManager._normalize_libraries(profile)
    downloads = normalized["libraries"][0]["downloads"]

    assert downloads["artifact"] == artifact
    assert calls[0]["path"].name == "hybrid-1.0-natives-windows-64.jar"
    assert "natives-windows-64" in downloads["classifiers"]


def test_incomplete_windows_native_cache_is_invalidated(tmp_path: Path) -> None:
    cache = tmp_path / "forge.json"
    cache.write_text(
        '{"id":"forge-1.6.4-9.11.1.1345","mainClass":"net.minecraft.launchwrapper.Launch","libraries":[{"name":"net.minecraft:launchwrapper:1.8","downloads":{"artifact":{"path":"net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","url":"https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","sha1":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":100}}},{"name":"org.lwjgl.lwjgl:lwjgl-platform:2.9.0","natives":{"windows":"natives-windows"},"downloads":{}}],"forge":{"schemaVersion":1,"gameVersion":"1.6.4","loaderVersion":"9.11.1.1345"}}',
        encoding="utf-8",
    )

    assert ForgeVersionManager._load_cached(cache, "1.6.4", "9.11.1.1345") is None


def test_complete_windows_native_cache_is_reused(tmp_path: Path) -> None:
    cache = tmp_path / "forge.json"
    cache.write_text(
        '{"id":"forge-1.6.4-9.11.1.1345","mainClass":"net.minecraft.launchwrapper.Launch","libraries":[{"name":"net.minecraft:launchwrapper:1.8","downloads":{"artifact":{"path":"net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","url":"https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","sha1":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":100}}},{"name":"org.lwjgl.lwjgl:lwjgl-platform:2.9.0","natives":{"windows":"natives-windows"},"downloads":{"classifiers":{"natives-windows":{"path":"org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar","url":"https://libraries.minecraft.net/org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-windows.jar","sha1":"cccccccccccccccccccccccccccccccccccccccc","size":609967}}}}],"forge":{"schemaVersion":1,"gameVersion":"1.6.4","loaderVersion":"9.11.1.1345"}}',
        encoding="utf-8",
    )

    assert ForgeVersionManager._load_cached(cache, "1.6.4", "9.11.1.1345") is not None


def test_incomplete_legacy_launchwrapper_cache_is_invalidated(tmp_path: Path) -> None:
    cache = tmp_path / "forge.json"
    cache.write_text(
        '{"id":"forge-1.6.4-9.11.1.1345","mainClass":"net.minecraft.launchwrapper.Launch","libraries":[{"name":"net.minecraftforge:minecraftforge:9.11.1.1345"},{"name":"net.minecraft:launchwrapper:1.8"}],"forge":{"schemaVersion":1,"gameVersion":"1.6.4","loaderVersion":"9.11.1.1345"}}',
        encoding="utf-8",
    )

    assert ForgeVersionManager._load_cached(cache, "1.6.4", "9.11.1.1345") is None


def test_complete_legacy_launchwrapper_cache_is_reused(tmp_path: Path) -> None:
    cache = tmp_path / "forge.json"
    cache.write_text(
        '{"id":"forge-1.6.4-9.11.1.1345","mainClass":"net.minecraft.launchwrapper.Launch","libraries":[{"name":"net.minecraftforge:minecraftforge:9.11.1.1345"},{"name":"net.minecraft:launchwrapper:1.8","downloads":{"artifact":{"path":"net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","url":"https://libraries.minecraft.net/net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar","sha1":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":100}}}],"forge":{"schemaVersion":1,"gameVersion":"1.6.4","loaderVersion":"9.11.1.1345"}}',
        encoding="utf-8",
    )

    assert ForgeVersionManager._load_cached(cache, "1.6.4", "9.11.1.1345") is not None


def test_detects_unsupported_install_client_error() -> None:
    output = "joptsimple.UnrecognizedOptionException: 'installClient' is not a recognized option"

    assert ForgeVersionManager._is_unsupported_install_client(output) is True


def test_repair_restores_previous_profile_when_reinstall_fails(monkeypatch, tmp_path: Path) -> None:
    base = make_version(tmp_path)
    cache = tmp_path / "forge-profile.json"
    previous = b'{"old": true}\n'
    cache.write_bytes(previous)
    forge_root = tmp_path / "forge"
    monkeypatch.setattr(Paths, "forge_version_json", staticmethod(lambda game, loader: cache))
    monkeypatch.setattr(Paths, "forge_root", staticmethod(lambda: forge_root))
    monkeypatch.setattr(ForgeVersionManager, "install", staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("installer failed"))))

    import pytest
    with pytest.raises(RuntimeError, match="installer failed"):
        ForgeVersionManager.repair(base, "47.3.0")

    assert cache.read_bytes() == previous
    assert "previous cached profile was restored" in (forge_root / "logs" / "forge-repair-1.20.1-47.3.0.log").read_text(encoding="utf-8")


def test_validate_installation_checks_profile_and_library_files(monkeypatch, tmp_path: Path) -> None:
    import hashlib

    libraries = tmp_path / "libraries"
    artifact = libraries / "net/minecraftforge/forge/1.20.1-47.3.0/forge-1.20.1-47.3.0.jar"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"forge")
    sha1 = hashlib.sha1(b"forge", usedforsecurity=False).hexdigest()
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: libraries))
    raw = make_version(tmp_path).raw_json
    raw = dict(raw)
    raw["id"] = "forge-1.20.1-47.3.0"
    raw["mainClass"] = "cpw.mods.bootstraplauncher.BootstrapLauncher"
    raw["forge"] = {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.3.0"}
    raw["libraries"] = [
        {
            "name": "net.minecraftforge:forge:1.20.1-47.3.0",
            "downloads": {
                "artifact": {
                    "path": "net/minecraftforge/forge/1.20.1-47.3.0/forge-1.20.1-47.3.0.jar",
                    "sha1": sha1,
                    "size": 5,
                }
            },
        }
    ]
    version = make_version(tmp_path)
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    assert ForgeVersionManager.validate_installation(version, "1.20.1", "47.3.0", verify_files=True) == []

    artifact.write_bytes(b"broken")
    issues = ForgeVersionManager.validate_installation(version, "1.20.1", "47.3.0", verify_files=True)
    assert any("wrong size" in issue or "SHA-1" in issue for issue in issues)


def test_validate_installation_accepts_modern_forge_runtime_components(tmp_path: Path) -> None:
    raw = make_version(tmp_path).raw_json
    raw = dict(raw)
    raw["id"] = "forge-1.20.1-47.4.21"
    raw["mainClass"] = "cpw.mods.bootstraplauncher.BootstrapLauncher"
    raw["forge"] = {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.4.21"}
    raw["libraries"] = [{"name": "net.minecraftforge:fmlloader:1.20.1-47.4.21"}]
    version = make_version(tmp_path)
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    assert ForgeVersionManager.validate_installation(version, "1.20.1", "47.4.21", verify_files=False) == []


def test_validate_installation_ignores_libraries_for_other_operating_systems(monkeypatch, tmp_path: Path) -> None:
    libraries = tmp_path / "libraries"
    forge_path = libraries / "net/minecraftforge/fmlloader/1.20.1-47.4.21/fmlloader-1.20.1-47.4.21.jar"
    forge_path.parent.mkdir(parents=True)
    forge_path.write_bytes(b"forge-runtime")
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: libraries))
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_os",
        staticmethod(lambda: "windows"),
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_arch",
        staticmethod(lambda: "x64"),
    )

    raw = make_version(tmp_path).raw_json
    raw = dict(raw)
    raw["id"] = "forge-1.20.1-47.4.21"
    raw["mainClass"] = "cpw.mods.bootstraplauncher.BootstrapLauncher"
    raw["forge"] = {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.4.21"}
    raw["libraries"] = [
        {
            "name": "net.minecraftforge:fmlloader:1.20.1-47.4.21",
            "downloads": {
                "artifact": {
                    "path": "net/minecraftforge/fmlloader/1.20.1-47.4.21/fmlloader-1.20.1-47.4.21.jar",
                    "sha1": "",
                    "size": len(b"forge-runtime"),
                }
            },
        },
        {
            "name": "ca.weblite:java-objc-bridge:1.1",
            "rules": [{"action": "allow", "os": {"name": "osx"}}],
            "downloads": {
                "artifact": {
                    "path": "ca/weblite/java-objc-bridge/1.1/java-objc-bridge-1.1.jar",
                    "sha1": "",
                    "size": 1,
                }
            },
        },
        {
            "name": "org.lwjgl:lwjgl-glfw:3.3.1:natives-linux",
            "rules": [{"action": "allow", "os": {"name": "linux"}}],
            "downloads": {
                "artifact": {
                    "path": "org/lwjgl/lwjgl-glfw/3.3.1/lwjgl-glfw-3.3.1-natives-linux.jar",
                    "sha1": "",
                    "size": 1,
                }
            },
        },
    ]
    version = make_version(tmp_path)
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    assert ForgeVersionManager.validate_installation(version, "1.20.1", "47.4.21", verify_files=True) == []


def test_validate_installation_still_reports_missing_current_os_library(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_os",
        staticmethod(lambda: "windows"),
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.LibraryRuleManager._get_current_arch",
        staticmethod(lambda: "x64"),
    )

    raw = make_version(tmp_path).raw_json
    raw = dict(raw)
    raw["id"] = "forge-1.20.1-47.4.21"
    raw["mainClass"] = "cpw.mods.bootstraplauncher.BootstrapLauncher"
    raw["forge"] = {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.4.21"}
    raw["libraries"] = [
        {"name": "net.minecraftforge:fmlloader:1.20.1-47.4.21"},
        {
            "name": "com.example:windows-only:1.0",
            "rules": [{"action": "allow", "os": {"name": "windows"}}],
            "downloads": {
                "artifact": {
                    "path": "com/example/windows-only/1.0/windows-only-1.0.jar",
                    "sha1": "",
                    "size": 1,
                }
            },
        },
    ]
    version = make_version(tmp_path)
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    issues = ForgeVersionManager.validate_installation(version, "1.20.1", "47.4.21", verify_files=True)

    assert issues == ["Missing required library: com/example/windows-only/1.0/windows-only-1.0.jar"]


def test_validate_installation_accepts_pre_1_7_minecraftforge_runtime(tmp_path: Path) -> None:
    raw = make_version(tmp_path).raw_json.copy()
    raw.update({
        "id": "1.6.4-Forge9.11.1.1345",
        "mainClass": "net.minecraft.launchwrapper.Launch",
        "forge": {"schemaVersion": 1, "gameVersion": "1.6.4", "loaderVersion": "9.11.1.1345"},
        "libraries": [{"name": "net.minecraftforge:minecraftforge:9.11.1.1345"}],
        "minecraftArguments": "--username ${auth_player_name} --tweakClass cpw.mods.fml.common.launcher.FMLTweaker",
    })
    version = make_version(tmp_path)
    version.id = raw["id"]
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    assert ForgeVersionManager.validate_installation(version, "1.6.4", "9.11.1.1345", verify_files=False) == []


def test_run_installer_reports_java_runner_output_on_failure(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from src.core.modloader.java_installer_runner import ModLoaderInstallerResult

    installer = tmp_path / "forge-installer.jar"
    installer.write_bytes(b"not-a-legacy-installer")
    forge_root = tmp_path / "forge-root"
    monkeypatch.setattr(Paths, "forge_root", staticmethod(lambda: forge_root))
    monkeypatch.setattr(
        "src.core.modloader.forge.forge_version_manager.ModLoaderJavaRunner.run",
        staticmethod(lambda *args, **kwargs: ModLoaderInstallerResult(1, "installer line\nfinal Forge detail", Path("java"), 1)),
    )

    with pytest.raises(RuntimeError, match="final Forge detail"):
        ForgeVersionManager._run_installer(make_version(tmp_path), "47.3.0", installer, tmp_path / "staging", None)

    assert "final Forge detail" in (forge_root / "logs" / "forge-1.20.1-47.3.0.log").read_text(encoding="utf-8")


def test_incomplete_cached_profile_is_refreshed_without_rerunning_forge_installer(monkeypatch, tmp_path: Path) -> None:
    import json

    cache = tmp_path / "forge-1.20.1-47.3.0.json"
    raw = make_version(tmp_path).raw_json.copy()
    raw.update({
        "id": "forge-1.20.1-47.3.0",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "libraries": [
            {"name": "net.minecraftforge:forge:1.20.1-47.3.0", "downloads": {"artifact": {"path": "net/minecraftforge/forge/1.20.1-47.3.0/forge-1.20.1-47.3.0.jar", "url": "https://maven.minecraftforge.net/forge.jar", "sha1": "a" * 40, "size": 1}}},
            {"name": "org.lwjgl:lwjgl:3.3.1", "natives": {"windows": "natives-windows"}, "downloads": {}},
        ],
        "forge": {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.3.0"},
    })
    cache.write_text(json.dumps(raw), encoding="utf-8")

    monkeypatch.setattr(Paths, "forge_version_json", staticmethod(lambda *_args: cache))
    monkeypatch.setattr("src.core.modloader.forge.forge_version_manager.VersionManager.load", staticmethod(lambda _version: make_version(tmp_path)))
    monkeypatch.setattr(ForgeVersionManager, "_download_installer", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Forge installer must not run"))))

    def refresh(data, _reporter=None):
        refreshed = json.loads(json.dumps(data))
        refreshed["libraries"][1]["downloads"] = {
            "artifact": {"path": "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1.jar", "url": "https://libraries.minecraft.net/lwjgl.jar", "sha1": "b" * 40, "size": 1},
            "classifiers": {"natives-windows": {"path": "org/lwjgl/lwjgl/3.3.1/lwjgl-3.3.1-natives-windows.jar", "url": "https://libraries.minecraft.net/lwjgl-native.jar", "sha1": "c" * 40, "size": 1}},
        }
        return refreshed

    monkeypatch.setattr(ForgeVersionManager, "_normalize_libraries", staticmethod(refresh))

    version = ForgeVersionManager.load("1.20.1", "47.3.0")

    assert version.id == "forge-1.20.1-47.3.0"
    assert ForgeVersionManager._load_cached(cache, "1.20.1", "47.3.0") is not None


def test_prepare_staging_reuses_cached_vanilla_libraries(monkeypatch, tmp_path: Path) -> None:
    version = make_version(tmp_path)
    cached_client = tmp_path / "cache" / f"{version.id}.jar"
    cached_client.parent.mkdir(parents=True, exist_ok=True)
    cached_client.write_bytes(b"client")
    libraries = tmp_path / "libraries"
    cached_library = libraries / "com/example/base/1.0/base-1.0.jar"
    cached_library.parent.mkdir(parents=True, exist_ok=True)
    cached_library.write_bytes(b"cached-base-library")
    monkeypatch.setattr(Paths, "client", staticmethod(lambda current: cached_client))
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: libraries))

    staging = tmp_path / "staging-cache"
    staging.mkdir()
    ForgeVersionManager._prepare_staging(version, staging)

    assert (staging / "libraries/com/example/base/1.0/base-1.0.jar").read_bytes() == b"cached-base-library"
