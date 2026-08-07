from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.atlauncher.atlauncher_client import ATLauncherClient
from src.core.atlauncher.atlauncher_pack_installer import ATLauncherPackInstaller
from src.core.atlauncher.atlauncher_pack_registry import ATLauncherPackRegistry
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.atlauncher.pack import ATLauncherPack
from src.models.atlauncher.version import ATLauncherFile, ATLauncherVersion
from src.models.instance.instance import Instance


def atl_file(name: str, *, optional: bool = False, selected: bool = False, server_only: bool = False, download_type: str = "direct") -> ATLauncherFile:
    return ATLauncherFile(
        file_id=name,
        name=name,
        path=f"mods/{name}",
        urls=(f"https://cdn.example/{name}",),
        md5="a" * 32,
        size=10,
        optional=optional,
        selected=selected,
        recommended=selected,
        server_only=server_only,
        download_type=download_type,
    )


def atl_version(files: tuple[ATLauncherFile, ...], unsupported: tuple[str, ...] = ()) -> ATLauncherVersion:
    return ATLauncherVersion(
        pack_id="25",
        safe_name="ExamplePack",
        version_id="101",
        version="2.0.0",
        minecraft_version="1.20.1",
        changelog="",
        recommended=True,
        development=False,
        loader="forge",
        loader_version="47.4.0",
        files=files,
        recommended_memory_mb=6144,
        unsupported_actions=unsupported,
    )


def test_select_files_respects_optional_and_server_flags() -> None:
    required = atl_file("required.jar")
    optional = atl_file("optional.jar", optional=True, selected=True)
    server = atl_file("server.jar", server_only=True)

    selected, skipped_optional, skipped_server, manual = ATLauncherPackInstaller._select_files(atl_version((required, optional, server)), False)

    assert selected == (required,)
    assert skipped_optional == 1
    assert skipped_server == 1
    assert manual == ()


def test_select_files_rejects_browser_and_unsafe_destinations() -> None:
    browser = atl_file("manual.jar", download_type="browser")
    selected, _, _, manual = ATLauncherPackInstaller._select_files(atl_version((browser,)), True)
    assert selected == (browser,)
    assert manual == (browser,)

    unsafe = ATLauncherFile("bad", "bad.jar", "../bad.jar", ("https://example/bad.jar",), md5="a" * 32)
    with pytest.raises(RuntimeError, match="Unsafe path"):
        ATLauncherPackInstaller._select_files(atl_version((unsafe,)), True)


def test_install_creates_deferred_registry(monkeypatch, tmp_path: Path) -> None:
    project = ATLauncherPack("25", "ExamplePack", "Example Pack", icon_url="https://cdn.example/icon.png")
    version = atl_version((atl_file("required.jar"),))
    saved: list[dict] = []

    monkeypatch.setattr(ATLauncherClient, "get_project", staticmethod(lambda *_args, **_kwargs: project))
    monkeypatch.setattr(ATLauncherClient, "get_version", staticmethod(lambda *_args, **_kwargs: version))
    monkeypatch.setattr(InstanceManager, "is_instance_exist", staticmethod(lambda _name: False))
    monkeypatch.setattr(VersionManager, "load", staticmethod(lambda version_id: SimpleNamespace(id=version_id)))
    monkeypatch.setattr(ModLoaderManager, "resolve", staticmethod(lambda *_args: ("forge", "47.4.0")))

    def create_instance(**kwargs):
        instance = Instance("id", kwargs["name"], "1.20.1", tmp_path / kwargs["name"], ("forge", "47.4.0"))
        instance.instance_dir.mkdir(parents=True, exist_ok=True)
        return instance

    monkeypatch.setattr(InstanceManager, "create", staticmethod(create_instance))
    monkeypatch.setattr(InstanceManager, "delete_instance", staticmethod(lambda _name: True))
    monkeypatch.setattr(InstanceArtworkManager, "apply_provider_artwork", staticmethod(lambda *_args, **_kwargs: False))
    settings: list[dict] = []
    monkeypatch.setattr(ATLauncherPackRegistry, "save", staticmethod(lambda _instance, data: saved.append(data)))
    monkeypatch.setattr(ModProvenanceRegistry, "synchronize", staticmethod(lambda _instance: {}))
    monkeypatch.setattr(InstanceManager, "default_instance_settings", staticmethod(lambda: {"java": {"path": "", "min_memory": 1024, "max_memory": 2048, "arguments": []}, "window": {}, "launch": {}}))
    monkeypatch.setattr(SettingsManager, "save_dict", staticmethod(lambda _instance, data: settings.append(data)))

    result = ATLauncherPackInstaller.install("ExamplePack", "2.0.0", "Example Pack")

    assert result.instance.name == "Example Pack"
    assert saved[0]["safeName"] == "ExamplePack"
    assert saved[0]["managedFiles"][0]["pendingDownload"] is True
    assert settings[0]["java"]["max_memory"] == 6144
    assert not (result.instance.instance_dir / "mods" / "required.jar").exists()


def test_install_rejects_unsupported_pack_actions(monkeypatch) -> None:
    project = ATLauncherPack("25", "ExamplePack", "Example Pack")
    version = atl_version((), ("custom-main-class",))
    monkeypatch.setattr(ATLauncherClient, "get_project", staticmethod(lambda *_args, **_kwargs: project))
    monkeypatch.setattr(ATLauncherClient, "get_version", staticmethod(lambda *_args, **_kwargs: version))
    monkeypatch.setattr(InstanceManager, "is_instance_exist", staticmethod(lambda _name: False))

    with pytest.raises(RuntimeError, match="not supported in this beta"):
        ATLauncherPackInstaller.install("ExamplePack", "2.0.0", "Example Pack")
