from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modrinth.modrinth_manual_installer import ModrinthManualInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.network.download_pause import download_pause_controller
from src.models.instance.instance import Instance
from src.models.modrinth.manual_download import ModrinthManualDownload


def _requirement(source: Path) -> ModrinthManualDownload:
    return ModrinthManualDownload(
        project_id="project",
        version_id="version",
        project_name="Restricted",
        file_name=source.name,
        file_size=source.stat().st_size,
        sha1=hashlib.sha1(source.read_bytes()).hexdigest(),
        sha512="",
        project_url="https://example.invalid/project",
        direct_url="",
        version_url="https://example.invalid/version",
        reason="manual",
        managed_kind="pack",
        managed_path=f"mods/{source.name}",
    )


def test_manual_import_can_use_owned_preparing_launch_lock(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.15.11"))
    source = tmp_path / "restricted.jar"
    source.write_bytes(b"manual during paused launch")
    requirement = _requirement(source)
    ModrinthPackRegistry.save(instance_dir, {"managedFiles": [{"path": f"mods/{source.name}", "sha1": "", "sha512": "", "size": source.stat().st_size}]})

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: True))
    monkeypatch.setattr(InstanceRunLock, "owns_preparing_lock", staticmethod(lambda _instance, token: token == "owned-token"))
    download_pause_controller.begin()
    assert download_pause_controller.request_pause() is True
    try:
        assert ModrinthManualInstaller.install(instance, requirement, source, launch_lock_token="owned-token") == source.name
    finally:
        download_pause_controller.finish()


def test_manual_import_rejects_unowned_active_launch_lock(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.15.11"))
    source = tmp_path / "restricted.jar"
    source.write_bytes(b"manual")
    requirement = _requirement(source)

    monkeypatch.setattr(InstanceRunLock, "is_active", staticmethod(lambda _instance: True))
    monkeypatch.setattr(InstanceRunLock, "owns_preparing_lock", staticmethod(lambda _instance, _token: False))

    with pytest.raises(RuntimeError, match="Close Minecraft"):
        ModrinthManualInstaller.install(instance, requirement, source, launch_lock_token="wrong-token")
