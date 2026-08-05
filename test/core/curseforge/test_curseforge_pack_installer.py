from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import json
import zipfile

import pytest

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_pack_installer import CurseForgePackInstaller
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.curseforge.file import CurseForgeFile
from src.models.instance.instance import Instance


def test_parses_primary_forge_loader() -> None:
    manifest = {
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [
                {"id": "forge-47.3.0", "primary": True},
                {"id": "forge-47.2.0", "primary": False},
            ],
        }
    }

    assert CurseForgePackInstaller._parse_loader(manifest) == ("1.20.1", "forge", "47.3.0")


def test_parses_primary_fabric_loader() -> None:
    manifest = {"minecraft": {"version": "1.20.1", "modLoaders": [{"id": "fabric-0.16.0", "primary": True}]}}

    assert CurseForgePackInstaller._parse_loader(manifest) == ("1.20.1", "fabric", "0.16.0")


def test_parses_primary_neoforge_loader() -> None:
    manifest = {"minecraft": {"version": "1.21.1", "modLoaders": [{"id": "neoforge-21.1.200", "primary": True}]}}

    assert CurseForgePackInstaller._parse_loader(manifest) == ("1.21.1", "neoforge", "21.1.200")



def test_parses_primary_quilt_loader() -> None:
    manifest = {"minecraft": {"version": "1.20.1", "modLoaders": [{"id": "quilt-0.27.1", "primary": True}]}}

    assert CurseForgePackInstaller._parse_loader(manifest) == ("1.20.1", "quilt", "0.27.1")

def test_rejects_ambiguous_or_unsupported_modpack_loaders() -> None:
    mixed = {
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [
                {"id": "fabric-0.16.0"},
                {"id": "forge-47.3.0"},
            ],
        }
    }
    unsupported = {
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [
                {"id": "liteloader-1.12.2", "primary": True},
            ],
        }
    }

    with pytest.raises(RuntimeError, match="multiple supported mod-loader families"):
        CurseForgePackInstaller._parse_loader(mixed)
    with pytest.raises(RuntimeError, match="unsupported loader"):
        CurseForgePackInstaller._parse_loader(unsupported)


def test_rejects_modpack_when_browser_loader_filter_does_not_match_manifest() -> None:
    with pytest.raises(RuntimeError, match="browser filter is set to Forge"):
        CurseForgePackInstaller._validate_expected_loader("fabric", "forge")


def test_installs_fabric_modpack_as_fabric_instance(tmp_path: Path, monkeypatch) -> None:
    pack_path = tmp_path / "fabric-pack.zip"
    manifest = {
        "minecraft": {
            "version": "1.20.1",
            "modLoaders": [{"id": "fabric-0.16.0", "primary": True}],
        },
        "files": [],
        "overrides": "overrides",
    }
    with zipfile.ZipFile(pack_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("overrides/config/example.json", "{}")

    calls: list[tuple[str, ...]] = []
    base_version = SimpleNamespace(id="1.20.1")
    project = SimpleNamespace(name="Fabric Pack", logo_url="https://cdn.example/curseforge.png")
    file = SimpleNamespace(display_name="Fabric Pack 1.0")

    def create_instance(name: str, version: object, mod_loader: tuple[str, str]) -> Instance:
        instance_dir = tmp_path / "instances" / name
        instance_dir.mkdir(parents=True)
        return Instance(
            instance_id="fabric-pack",
            name=name,
            version_id=version.id,
            instance_dir=instance_dir,
            mod_loader=mod_loader,
        )

    monkeypatch.setattr(CurseForgePackInstaller, "_resolve_files", staticmethod(lambda *_args, **_kwargs: ([], 0)))
    monkeypatch.setattr(VersionManager, "load", staticmethod(lambda version_id: base_version))
    monkeypatch.setattr(
        ModLoaderManager,
        "resolve",
        staticmethod(
            lambda game_version, loader_name, loader_version="auto": (
                calls.append(("resolve", game_version, loader_name, loader_version))
                or (loader_name, loader_version)
            )
        ),
    )
    monkeypatch.setattr(
        ModLoaderManager,
        "prepare",
        staticmethod(
            lambda version, loader_name, loader_version, reporter=None: (
                calls.append(("prepare", loader_name, loader_version)) or version
            )
        ),
    )
    monkeypatch.setattr(InstanceManager, "create", staticmethod(create_instance))
    artwork_calls = []
    monkeypatch.setattr(InstanceArtworkManager, "apply_provider_artwork", classmethod(lambda cls, instance, provider, project_id, artwork_url, reporter=None: artwork_calls.append((provider, project_id, artwork_url)) or False))

    result = CurseForgePackInstaller._install_from_archive(
        11,
        22,
        "Fabric Instance",
        True,
        project,
        file,
        pack_path,
        None,
        expected_loader="fabric",
    )

    assert result.instance.mod_loader == ("fabric", "0.16.0")
    assert ("resolve", "1.20.1", "fabric", "0.16.0") in calls
    assert ("prepare", "fabric", "0.16.0") not in calls
    assert (result.instance.instance_dir / "config" / "example.json").is_file()
    registry = json.loads(
        (result.instance.instance_dir / ".mcw" / "curseforge-pack.json").read_text(encoding="utf-8")
    )
    assert registry["loader"] == "fabric"
    assert registry["loaderVersion"] == "0.16.0"
    assert artwork_calls == [("curseforge", 11, "https://cdn.example/curseforge.png")]


def test_installs_neoforge_modpack_as_neoforge_instance(tmp_path: Path, monkeypatch) -> None:
    pack_path = tmp_path / "neoforge-pack.zip"
    manifest = {
        "minecraft": {
            "version": "1.21.1",
            "modLoaders": [{"id": "neoforge-21.1.200", "primary": True}],
        },
        "files": [],
        "overrides": "overrides",
    }
    with zipfile.ZipFile(pack_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("overrides/config/neoforge.toml", "enabled=true")

    calls: list[tuple[str, ...]] = []
    base_version = SimpleNamespace(id="1.21.1")
    project = SimpleNamespace(name="NeoForge Pack")
    file = SimpleNamespace(display_name="NeoForge Pack 1.0")

    def create_instance(name: str, version: object, mod_loader: tuple[str, str]) -> Instance:
        instance_dir = tmp_path / "instances" / name
        instance_dir.mkdir(parents=True)
        return Instance(instance_id="neoforge-pack", name=name, version_id=version.id, instance_dir=instance_dir, mod_loader=mod_loader)

    monkeypatch.setattr(CurseForgePackInstaller, "_resolve_files", staticmethod(lambda *_args, **_kwargs: ([], 0)))
    monkeypatch.setattr(VersionManager, "load", staticmethod(lambda version_id: base_version))
    monkeypatch.setattr(ModLoaderManager, "resolve", staticmethod(lambda game_version, loader_name, loader_version="auto": calls.append(("resolve", game_version, loader_name, loader_version)) or (loader_name, loader_version)))
    monkeypatch.setattr(ModLoaderManager, "prepare", staticmethod(lambda version, loader_name, loader_version, reporter=None: calls.append(("prepare", loader_name, loader_version)) or version))
    monkeypatch.setattr(InstanceManager, "create", staticmethod(create_instance))

    result = CurseForgePackInstaller._install_from_archive(31, 32, "NeoForge Instance", True, project, file, pack_path, None, expected_loader="neoforge")

    assert result.instance.mod_loader == ("neoforge", "21.1.200")
    assert ("resolve", "1.21.1", "neoforge", "21.1.200") in calls
    assert ("prepare", "neoforge", "21.1.200") not in calls
    assert (result.instance.instance_dir / "config" / "neoforge.toml").is_file()
    registry = json.loads((result.instance.instance_dir / ".mcw" / "curseforge-pack.json").read_text(encoding="utf-8"))
    assert registry["loader"] == "neoforge"
    assert registry["loaderVersion"] == "21.1.200"


@pytest.mark.parametrize("value", ["../outside", "/absolute", "C:/windows", "folder/../../escape", ""])
def test_rejects_unsafe_override_paths(value: str) -> None:
    with pytest.raises(RuntimeError, match="Unsafe"):
        CurseForgePackInstaller._safe_relative_path(value)


def test_accepts_safe_override_path() -> None:
    assert CurseForgePackInstaller._safe_relative_path("config/example.toml") == PurePosixPath("config/example.toml")


@pytest.mark.parametrize("value", ["settings.json", "instance.json", ".mcw/registry.json"])
def test_rejects_launcher_owned_override_paths(value: str) -> None:
    with pytest.raises(RuntimeError, match="Reserved"):
        CurseForgePackInstaller._safe_relative_path(value)


def test_resolve_files_keeps_advisory_loader_and_game_version_metadata(monkeypatch) -> None:
    file = CurseForgeFile(
        file_id=20,
        project_id=10,
        display_name="Universal build labelled as Fabric",
        file_name="universal.jar",
        release_type="release",
        file_date="2026-07-25T00:00:00Z",
        file_length=100,
        download_url="https://example.invalid/universal.jar",
        sha1="a" * 40,
        game_versions=("1.20.4",),
        dependencies=(),
        loaders=("fabric",),
    )
    monkeypatch.setattr(CurseForgeClient, "get_files_batch", staticmethod(lambda ids: {20: file}))

    files, skipped = CurseForgePackInstaller._resolve_files(
        {"files": [{"projectID": 10, "fileID": 20, "required": True}]},
        game_version="1.20.1",
        install_optional_files=True,
        reporter=None,
    )

    assert skipped == 0
    assert files[0]["declaredLoaders"] == ["fabric"]
    assert files[0]["gameVersions"] == ["1.20.4"]
    assert files[0]["fileName"] == "universal.jar"


def test_manual_modpack_download_becomes_resumable_request(monkeypatch, tmp_path) -> None:
    from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
    from src.core.curseforge.curseforge_pack_installer import CurseForgeModpackManualDownloadRequired
    from src.core.fs.paths import Paths
    from src.models.curseforge.manual_download import CurseForgeManualDownload

    project = SimpleNamespace(name="Restricted Pack", project_url="https://www.curseforge.com/minecraft/modpacks/restricted-pack")
    file = CurseForgeFile(
        file_id=22,
        project_id=11,
        display_name="Restricted Pack 1.0",
        file_name="restricted-pack.zip",
        release_type="release",
        file_date="2026-07-26T00:00:00Z",
        file_length=123,
        download_url="",
        sha1="a" * 40,
        game_versions=("1.18.2",),
        dependencies=(),
        is_available=False,
        loaders=("forge",),
    )
    requirement = CurseForgeManualDownload(
        project_id=11,
        file_id=22,
        project_name="Restricted Pack",
        file_name=file.file_name,
        file_size=file.file_length,
        sha1=file.sha1,
        project_url=project.project_url,
        reason="Manual download required",
    )
    monkeypatch.setattr(InstanceManager, "is_instance_exist", staticmethod(lambda _name: False))
    monkeypatch.setattr(CurseForgeClient, "normalize_release_types", staticmethod(lambda _values: ("release",)))
    monkeypatch.setattr(CurseForgeClient, "get_project", staticmethod(lambda _project_id: project))
    monkeypatch.setattr(CurseForgeClient, "get_file", staticmethod(lambda _project_id, _file_id: file))
    monkeypatch.setattr(Paths, "curseforge_pack_cache", staticmethod(lambda *_args: tmp_path / file.file_name))
    monkeypatch.setattr(CurseForgeDownloader, "download_file", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(CurseForgeManualDownloadRequired(requirement))))

    with pytest.raises(CurseForgeModpackManualDownloadRequired) as raised:
        CurseForgePackInstaller.install(
            11,
            22,
            "Restricted Pack",
            allowed_release_types=("release",),
            expected_loader="fabric",
        )

    request = raised.value
    assert request.instance_name == "Restricted Pack"
    assert request.requirement.managed_kind == "modpack_archive"
    assert request.requirement.project_url.endswith("/files/22")
    assert request.allowed_release_types == ("release",)
    assert request.expected_loader == "fabric"


def test_manual_modpack_archive_is_verified_cached_and_resumed(monkeypatch, tmp_path) -> None:
    from hashlib import sha1
    from types import SimpleNamespace

    from src.core.curseforge.curseforge_pack_installer import CurseForgeModpackManualDownloadRequired
    from src.core.fs.paths import Paths
    from src.models.curseforge.manual_download import CurseForgeManualDownload

    payload = b"downloaded CurseForge modpack"
    source = tmp_path / "downloaded-pack.zip"
    source.write_bytes(payload)
    project = SimpleNamespace(name="Restricted Pack", project_url="https://www.curseforge.com/minecraft/modpacks/restricted-pack")
    file = CurseForgeFile(
        file_id=22,
        project_id=11,
        display_name="Restricted Pack 1.0",
        file_name="restricted-pack.zip",
        release_type="release",
        file_date="2026-07-26T00:00:00Z",
        file_length=len(payload),
        download_url="",
        sha1=sha1(payload, usedforsecurity=False).hexdigest(),
        game_versions=("1.18.2",),
        dependencies=(),
        is_available=False,
        loaders=("forge",),
    )
    requirement = CurseForgeManualDownload(
        project_id=11,
        file_id=22,
        project_name=project.name,
        file_name=file.file_name,
        file_size=file.file_length,
        sha1=file.sha1,
        project_url=project.project_url + "/files/22",
        reason="Manual download required",
        managed_kind="modpack_archive",
    )
    request = CurseForgeModpackManualDownloadRequired(requirement, 11, 22, "Restricted Pack", True, ("release",))
    cache_path = tmp_path / "cache" / file.file_name
    sentinel = object()
    monkeypatch.setattr(CurseForgePackInstaller, "_prepare_install", staticmethod(lambda *_args, **_kwargs: ("Restricted Pack", ("release",), project, file)))
    monkeypatch.setattr(Paths, "curseforge_pack_cache", staticmethod(lambda *_args: cache_path))
    monkeypatch.setattr(CurseForgePackInstaller, "_install_from_archive", staticmethod(lambda *_args, **_kwargs: sentinel))

    result = CurseForgePackInstaller.install_manual_archive(request, source)

    assert result is sentinel
    assert cache_path.read_bytes() == payload


def test_local_curseforge_icon_uses_reliable_project_id_only(tmp_path: Path, monkeypatch) -> None:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="cf", name="CF", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("forge", "47"))
    package = tmp_path / "pack.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", "{}")
    calls: list[tuple] = []
    monkeypatch.setattr(InstanceArtworkManager, "apply_embedded_archive_artwork", classmethod(lambda cls, _instance, _archive: False))
    monkeypatch.setattr(InstanceArtworkManager, "has_custom_artwork", classmethod(lambda cls, _instance: False))
    monkeypatch.setattr(InstanceArtworkManager, "apply_provider_artwork", classmethod(lambda cls, *args, **kwargs: calls.append(args) or False))
    monkeypatch.setattr(InstanceManager, "load", staticmethod(lambda _name: instance))
    monkeypatch.setattr(CurseForgeClient, "get_project", staticmethod(lambda project_id: SimpleNamespace(logo_url="https://cdn.example/cf.png")))

    with zipfile.ZipFile(package) as archive:
        CurseForgePackInstaller._apply_local_archive_artwork(instance, archive, 42, None)
    assert calls and calls[0][1:4] == ("curseforge", 42, "https://cdn.example/cf.png")

    calls.clear()
    with zipfile.ZipFile(package) as archive:
        CurseForgePackInstaller._apply_local_archive_artwork(instance, archive, 0, None)
    assert calls == []


def test_manifest_project_id_does_not_guess_from_pack_name() -> None:
    assert CurseForgePackInstaller._manifest_project_id({"name": "Popular Pack"}) == 0
    assert CurseForgePackInstaller._manifest_project_id({"projectID": 123}) == 123
    assert CurseForgePackInstaller._manifest_project_id({"projectId": "456"}) == 456
