from __future__ import annotations

from pathlib import Path
import json
import zipfile

import pytest

from src.core.backup.instance_backup_manager import InstanceBackupManager
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.models.instance.instance import Instance


@pytest.fixture
def instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Instance:
    instance_dir = tmp_path / "instances" / "Demo"
    instance_dir.mkdir(parents=True)
    (instance_dir / "instance.json").write_text('{"id":"id-1"}', encoding="utf-8")
    (instance_dir / "settings.json").write_text("settings-v1", encoding="utf-8")
    (instance_dir / "mods").mkdir()
    (instance_dir / "mods" / "demo.jar").write_bytes(b"mod-v1")
    (instance_dir / "saves" / "World").mkdir(parents=True)
    (instance_dir / "saves" / "World" / "level.dat").write_bytes(b"world-v1")
    (instance_dir / "logs").mkdir()
    (instance_dir / "logs" / "latest.log").write_text("keep-log", encoding="utf-8")
    monkeypatch.setattr(Paths, "BACKUPS_ROOT", tmp_path / "backups")
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(InstanceRunLock, "is_active", lambda _instance: False)
    return Instance(instance_id="id-1", name="Demo", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def test_full_backup_restore_is_transactional_and_preserves_protected_files(instance: Instance) -> None:
    result = InstanceBackupManager.create(instance, "full")
    assert result.backup.path.is_file()
    (instance.instance_dir / "settings.json").write_text("settings-v2", encoding="utf-8")
    (instance.instance_dir / "mods" / "demo.jar").write_bytes(b"mod-v2")
    (instance.instance_dir / "extra.txt").write_text("new", encoding="utf-8")
    (instance.instance_dir / "logs" / "latest.log").write_text("new-log", encoding="utf-8")
    (instance.instance_dir / "instance.json").write_text('{"id":"id-1","new":true}', encoding="utf-8")

    restored = InstanceBackupManager.restore(instance, result.backup.path, create_safety_backup=False)

    assert restored.scope == "full"
    assert (instance.instance_dir / "settings.json").read_text(encoding="utf-8") == "settings-v1"
    assert (instance.instance_dir / "mods" / "demo.jar").read_bytes() == b"mod-v1"
    assert not (instance.instance_dir / "extra.txt").exists()
    assert (instance.instance_dir / "logs" / "latest.log").read_text(encoding="utf-8") == "new-log"
    assert json.loads((instance.instance_dir / "instance.json").read_text(encoding="utf-8"))["new"] is True


def test_full_restore_copies_staged_directory_when_windows_blocks_rename(instance: Instance, monkeypatch: pytest.MonkeyPatch) -> None:
    fabric_dir = instance.instance_dir / ".fabric"
    fabric_dir.mkdir()
    fabric_state = fabric_dir / "state.json"
    fabric_state.write_text('{"state":"backup"}', encoding="utf-8")
    backup = InstanceBackupManager.create(instance, "full").backup.path
    fabric_state.write_text('{"state":"current"}', encoding="utf-8")
    original_rename = Path.rename
    blocked_paths: list[Path] = []

    def deny_staging_fabric_rename(source: Path, target: Path) -> Path:
        if source.name == ".fabric" and "staging" in source.parts and not source.parent.name.startswith("rollback-"):
            blocked_paths.append(source)
            raise PermissionError(13, "Access is denied", str(source), str(target))
        return original_rename(source, target)

    monkeypatch.setattr(Path, "rename", deny_staging_fabric_rename)

    InstanceBackupManager.restore(instance, backup, create_safety_backup=False)

    assert blocked_paths
    assert fabric_state.read_text(encoding="utf-8") == '{"state":"backup"}'


def test_world_backup_only_restores_saves(instance: Instance) -> None:
    backup = InstanceBackupManager.create(instance, "worlds").backup.path
    (instance.instance_dir / "saves" / "World" / "level.dat").write_bytes(b"world-v2")
    (instance.instance_dir / "mods" / "demo.jar").write_bytes(b"mod-v2")

    InstanceBackupManager.restore(instance, backup, create_safety_backup=False)

    assert (instance.instance_dir / "saves" / "World" / "level.dat").read_bytes() == b"world-v1"
    assert (instance.instance_dir / "mods" / "demo.jar").read_bytes() == b"mod-v2"


def test_restore_rejects_backup_from_another_instance(instance: Instance, tmp_path: Path) -> None:
    path = tmp_path / "foreign.mcwbackup"
    manifest = {"formatVersion": 1, "instanceId": "other", "instanceName": "Other", "scope": "full", "createdAt": "", "fileCount": 0, "totalSize": 0}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mcw-backup.json", json.dumps(manifest))
    with pytest.raises(RuntimeError, match="different instance"):
        InstanceBackupManager.restore(instance, path, create_safety_backup=False)


def test_restore_rejects_path_traversal(instance: Instance, tmp_path: Path) -> None:
    path = tmp_path / "evil.mcwbackup"
    manifest = {"formatVersion": 1, "instanceId": "id-1", "instanceName": "Demo", "scope": "full", "createdAt": "", "fileCount": 1, "totalSize": 4}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mcw-backup.json", json.dumps(manifest))
        archive.writestr("payload/../evil.txt", b"evil")
    with pytest.raises(RuntimeError, match="Unsafe path"):
        InstanceBackupManager.restore(instance, path, create_safety_backup=False)
