from pathlib import Path
import hashlib

import pytest

from src.core.fs.paths import Paths
from src.core.modloader.neoforge.neoforge_version_manager import NeoForgeVersionManager
from src.models.minecraft.version import Version


def make_version(tmp_path: Path) -> Version:
    raw = {
        "id": "1.21.1",
        "arguments": {"game": ["--demo"], "jvm": ["-Dbase=true"]},
        "libraries": [{"name": "com.example:base:1.0"}],
        "downloads": {"client": {"url": "https://example/client.jar", "sha1": "a" * 40, "size": 1}},
        "assetIndex": {"id": "1.21", "url": "https://example/assets.json", "sha1": "b" * 40, "size": 1},
        "assets": "1.21",
        "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {"majorVersion": 21},
    }
    return Version(id="1.21.1", arguments=raw["arguments"], minecraft_arguments=None, libraries=raw["libraries"], downloads=raw["downloads"], asset_index=raw["assetIndex"], assets=raw["assets"], main_class=raw["mainClass"], java_version=raw["javaVersion"], raw_json=raw, path=tmp_path / "1.21.1.json", type="release")


def test_merge_profiles_keeps_neoforge_as_distinct_loader() -> None:
    base = make_version(Path(".")).raw_json
    profile = {
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "arguments": {"game": ["--fml.neoForgeVersion", "21.1.200"], "jvm": ["-Dneoforge=true"]},
        "libraries": [{"name": "net.neoforged:neoforge:21.1.200"}],
    }

    merged = NeoForgeVersionManager._merge_profiles(base, profile, "1.21.1", "21.1.200")

    assert merged["id"] == "neoforge-1.21.1-21.1.200"
    assert merged["inheritsFrom"] == "1.21.1"
    assert merged["neoforge"]["loaderVersion"] == "21.1.200"
    assert "forge" not in merged
    assert merged["arguments"]["game"][-2:] == ["--fml.neoForgeVersion", "21.1.200"]


def test_neoforged_libraries_use_official_repository() -> None:
    assert NeoForgeVersionManager._library_repository({}, "net.neoforged:neoforge:21.1.200") == "https://maven.neoforged.net/releases/"


def test_validate_installation_accepts_neoforge_runtime(monkeypatch, tmp_path: Path) -> None:
    libraries = tmp_path / "libraries"
    artifact = libraries / "net/neoforged/neoforge/21.1.200/neoforge-21.1.200.jar"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"neoforge")
    sha1 = hashlib.sha1(b"neoforge", usedforsecurity=False).hexdigest()
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: libraries))
    raw = make_version(tmp_path).raw_json.copy()
    raw.update({
        "id": "neoforge-1.21.1-21.1.200",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "neoforge": {"schemaVersion": 1, "gameVersion": "1.21.1", "loaderVersion": "21.1.200"},
        "libraries": [{"name": "net.neoforged:neoforge:21.1.200", "downloads": {"artifact": {"path": "net/neoforged/neoforge/21.1.200/neoforge-21.1.200.jar", "sha1": sha1, "size": len(b"neoforge")}}}],
    })
    version = make_version(tmp_path)
    version.raw_json = raw
    version.main_class = raw["mainClass"]

    assert NeoForgeVersionManager.validate_installation(version, "1.21.1", "21.1.200", verify_files=True) == []


def test_find_profile_ignores_staged_vanilla_profile(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    vanilla = versions / "1.21.1" / "1.21.1.json"
    vanilla.parent.mkdir(parents=True)
    vanilla.write_text('{"id":"1.21.1","mainClass":"net.minecraft.client.main.Main"}', encoding="utf-8")

    try:
        NeoForgeVersionManager._find_profile(tmp_path, "1.21.1", "21.1.200")
    except RuntimeError as error:
        assert "NeoForge launch profile" in str(error)
    else:
        raise AssertionError("The staged Vanilla profile must not be accepted as NeoForge.")


def test_find_profile_accepts_neoforged_runtime_metadata(tmp_path: Path) -> None:
    profile_path = tmp_path / "versions" / "custom-profile" / "custom-profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        '{"id":"custom-profile","libraries":[{"name":"net.neoforged:neoforge:21.1.200"}]}',
        encoding="utf-8",
    )

    profile = NeoForgeVersionManager._find_profile(tmp_path, "1.21.1", "21.1.200")

    assert profile["id"] == "custom-profile"

def test_prepare_staging_writes_launcher_layout(monkeypatch, tmp_path: Path) -> None:
    version = make_version(tmp_path)
    cached_client = tmp_path / "cache" / "1.21.1.jar"
    cached_client.parent.mkdir()
    cached_client.write_bytes(b"client")
    monkeypatch.setattr(Paths, "client", staticmethod(lambda current: cached_client))

    staging = tmp_path / "staging"
    staging.mkdir()
    NeoForgeVersionManager._prepare_staging(version, staging)

    assert (staging / "launcher_profiles.json").is_file()
    assert (staging / "versions" / "1.21.1" / "1.21.1.json").is_file()
    assert (staging / "versions" / "1.21.1" / "1.21.1.jar").read_bytes() == b"client"


def test_normalize_legacy_library_builds_download_metadata(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "libraries"
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: root))
    sha1 = "a" * 40
    profile = {
        "libraries": [{
            "name": "net.neoforged:legacy:1.0",
            "url": "https://maven.neoforged.net/releases/",
            "checksums": [sha1],
        }]
    }

    normalized = NeoForgeVersionManager._normalize_libraries(profile)
    artifact = normalized["libraries"][0]["downloads"]["artifact"]

    assert artifact["path"] == "net/neoforged/legacy/1.0/legacy-1.0.jar"
    assert artifact["url"] == "https://maven.neoforged.net/releases/net/neoforged/legacy/1.0/legacy-1.0.jar"
    assert artifact["sha1"] == sha1
    assert artifact["size"] == 0


def test_repair_restores_previous_profile_when_reinstall_fails(monkeypatch, tmp_path: Path) -> None:
    base = make_version(tmp_path)
    cache = tmp_path / "neoforge-profile.json"
    previous = b'{"old": true}\n'
    cache.write_bytes(previous)
    neoforge_root = tmp_path / "neoforge"
    monkeypatch.setattr(Paths, "neoforge_version_json", staticmethod(lambda game, loader: cache))
    monkeypatch.setattr(Paths, "neoforge_root", staticmethod(lambda: neoforge_root))
    monkeypatch.setattr(NeoForgeVersionManager, "install", staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("installer failed"))))

    with pytest.raises(RuntimeError, match="installer failed"):
        NeoForgeVersionManager.repair(base, "21.1.200")

    assert cache.read_bytes() == previous
    assert "previous cached profile was restored" in (neoforge_root / "logs" / "neoforge-repair-1.21.1-21.1.200.log").read_text(encoding="utf-8")



def test_profile_match_accepts_rule_wrapped_game_arguments() -> None:
    profile = {
        "id": "custom-profile",
        "arguments": {
            "game": [
                {"rules": [{"action": "allow", "os": {"name": "windows"}}], "value": ["--fml.neoForgeVersion", "21.1.200"]},
            ]
        },
    }

    assert NeoForgeVersionManager._profile_matches_neoforge(profile, "custom-profile", "21.1.200") is True


def test_runtime_detection_accepts_rule_wrapped_game_arguments() -> None:
    raw = {
        "arguments": {
            "game": [
                {"rules": [{"action": "allow"}], "value": "--fml.neoForgeVersion"},
                {"rules": [{"action": "allow"}], "value": ["21.1.200"]},
            ]
        }
    }

    assert NeoForgeVersionManager._has_neoforge_runtime([], raw, "21.1.200") is True


def test_run_installer_reports_java_runner_output_on_failure(monkeypatch, tmp_path: Path) -> None:
    from src.core.modloader.java_installer_runner import ModLoaderInstallerResult

    installer = tmp_path / "neoforge-installer.jar"
    installer.write_bytes(b"not-a-legacy-installer")
    neoforge_root = tmp_path / "neoforge-root"
    monkeypatch.setattr(Paths, "neoforge_root", staticmethod(lambda: neoforge_root))
    monkeypatch.setattr(
        "src.core.modloader.neoforge.neoforge_version_manager.ModLoaderJavaRunner.run",
        staticmethod(lambda *args, **kwargs: ModLoaderInstallerResult(1, "installer line\nfinal NeoForge detail", Path("java"), 1)),
    )

    with pytest.raises(RuntimeError, match="final NeoForge detail"):
        NeoForgeVersionManager._run_installer(make_version(tmp_path), "21.1.200", installer, tmp_path / "staging", None)

    assert "final NeoForge detail" in (neoforge_root / "logs" / "neoforge-1.21.1-21.1.200.log").read_text(encoding="utf-8")


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
    NeoForgeVersionManager._prepare_staging(version, staging)

    assert (staging / "libraries/com/example/base/1.0/base-1.0.jar").read_bytes() == b"cached-base-library"
