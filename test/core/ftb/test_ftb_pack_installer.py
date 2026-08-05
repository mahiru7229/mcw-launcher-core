from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.ftb.ftb_client import FTBClient
from src.core.ftb.ftb_pack_installer import FTBPackInstaller
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.ftb.project import FTBProject
from src.models.ftb.version import FTBFile, FTBTarget, FTBVersion
from src.models.instance.instance import Instance


def ftb_file(file_id: int, name: str, path: str = "mods", *, optional: bool = False, server_only: bool = False) -> FTBFile:
    return FTBFile(
        file_id=file_id,
        name=name,
        path=path,
        version="1.0",
        file_type="mod",
        urls=(f"https://primary.example/{name}", f"https://mirror.example/{name}"),
        sha1=f"{file_id:x}".rjust(40, "0"),
        size=10,
        optional=optional,
        server_only=server_only,
    )


def ftb_version(files: tuple[FTBFile, ...]) -> FTBVersion:
    return FTBVersion(
        project_id=25,
        version_id=101,
        name="1.0.0",
        release_type="release",
        files=files,
        targets=(
            FTBTarget(1, "game", "minecraft", "1.20.1"),
            FTBTarget(2, "modloader", "forge", "47.4.0"),
        ),
        recommended_memory_mb=6144,
    )


def test_select_files_skips_server_and_optional_files() -> None:
    required = ftb_file(1, "required.jar")
    optional = ftb_file(2, "optional.jar", optional=True)
    server = ftb_file(3, "server.jar", server_only=True)

    selected, skipped_optional, skipped_server = FTBPackInstaller._select_files(ftb_version((required, optional, server)), False)

    assert selected == (required,)
    assert skipped_optional == 1
    assert skipped_server == 1


def test_select_files_rejects_unsafe_and_duplicate_destinations() -> None:
    with pytest.raises(RuntimeError, match="Unsafe path"):
        FTBPackInstaller._select_files(ftb_version((ftb_file(1, "evil.jar", "../mods"),)), True)

    with pytest.raises(RuntimeError, match="same destination"):
        FTBPackInstaller._select_files(ftb_version((ftb_file(1, "same.jar"), ftb_file(2, "same.jar"))), True)

    with pytest.raises(RuntimeError, match="Unsafe path"):
        FTBPackInstaller._select_files(ftb_version((ftb_file(1, "../evil.jar"),)), True)


def test_install_creates_deferred_registry_and_rolls_back_on_post_create_failure(monkeypatch, tmp_path: Path) -> None:
    project = FTBProject(project_id=25, name="FTB Example", icon_url="https://cdn.example/icon.png")
    version = ftb_version((ftb_file(1, "example.jar"),))
    deleted: list[str] = []
    saved: list[dict] = []
    settings_saved: list[dict] = []

    monkeypatch.setattr(FTBClient, "get_project", staticmethod(lambda _project_id: project))
    monkeypatch.setattr(FTBClient, "get_version", staticmethod(lambda _project_id, _version_id: version))
    monkeypatch.setattr(InstanceManager, "is_instance_exist", staticmethod(lambda _name: False))
    monkeypatch.setattr(VersionManager, "load", staticmethod(lambda version_id: SimpleNamespace(id=version_id)))
    monkeypatch.setattr(ModLoaderManager, "resolve", staticmethod(lambda *_args: ("forge", "47.4.0")))

    def create_instance(**kwargs):
        instance = Instance("id", kwargs["name"], "1.20.1", tmp_path / kwargs["name"], ("forge", "47.4.0"))
        instance.instance_dir.mkdir(parents=True, exist_ok=True)
        return instance

    monkeypatch.setattr(InstanceManager, "create", staticmethod(create_instance))
    monkeypatch.setattr(InstanceManager, "delete_instance", staticmethod(lambda name: deleted.append(name) or True))
    monkeypatch.setattr(InstanceArtworkManager, "apply_provider_artwork", staticmethod(lambda *_args, **_kwargs: False))
    monkeypatch.setattr(FTBPackRegistry, "save", staticmethod(lambda _instance, data: saved.append(data)))
    monkeypatch.setattr(SettingsManager, "save_dict", staticmethod(lambda _instance, data: settings_saved.append(data)))

    settings = {"java": {"min_memory": 2048, "max_memory": 6144}}
    result = FTBPackInstaller.install(25, 101, "FTB Example", settings_override=settings)

    assert result.instance.name == "FTB Example"
    assert not (result.instance.instance_dir / "mods" / "example.jar").exists()
    assert settings_saved == [settings]
    assert saved[0]["projectId"] == 25
    assert saved[0]["managedFiles"][0]["urls"] == list(version.files[0].urls)
    assert saved[0]["managedFiles"][0]["pendingDownload"] is True
    assert deleted == []

    monkeypatch.setattr(FTBPackRegistry, "save", staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("registry failed"))))
    with pytest.raises(OSError, match="registry failed"):
        FTBPackInstaller.install(25, 101, "FTB Example 2")
    assert deleted[-1] == "FTB Example 2"

