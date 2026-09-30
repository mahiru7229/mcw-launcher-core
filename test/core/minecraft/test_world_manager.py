from __future__ import annotations

import gzip
from pathlib import Path
import struct
import zipfile

import pytest

from mcw_core.api.minecraft.world_manager import WorldManager
from src.models.world.world_info import WorldInfo


def _build_dummy_level_dat(world_name: str, game_type: int = 0, hardcore: int = 0, last_played: int = 1700000000000) -> bytes:
    # Build minimal binary NBT: TAG_Compound with name "", containing TAG_Compound "Data"
    # Tag constants: TAG_Compound = 10, TAG_End = 0, TAG_String = 8, TAG_Int = 3, TAG_Byte = 1, TAG_Long = 4
    payload = bytearray()

    def write_string(s: str) -> None:
        encoded = s.encode("utf-8")
        payload.extend(struct.pack(">H", len(encoded)))
        payload.extend(encoded)

    # Root compound
    payload.append(10)  # TAG_Compound
    write_string("")     # name ""

    # "Data" compound
    payload.append(10)  # TAG_Compound
    write_string("Data")

    # LevelName string
    payload.append(8)   # TAG_String
    write_string("LevelName")
    write_string(world_name)

    # GameType int
    payload.append(3)   # TAG_Int
    write_string("GameType")
    payload.extend(struct.pack(">i", game_type))

    # hardcore byte
    payload.append(1)   # TAG_Byte
    write_string("hardcore")
    payload.append(hardcore)

    # LastPlayed long
    payload.append(4)   # TAG_Long
    write_string("LastPlayed")
    payload.extend(struct.pack(">q", last_played))

    # End Data compound
    payload.append(0)   # TAG_End

    # End Root compound
    payload.append(0)   # TAG_End

    return gzip.compress(bytes(payload))


def test_world_manager_read_world_info(tmp_path: Path) -> None:
    world_dir = tmp_path / "MySurvivalWorld"
    world_dir.mkdir()
    level_dat = world_dir / "level.dat"
    level_dat.write_bytes(_build_dummy_level_dat("Super Adventure", game_type=1, hardcore=0, last_played=1710000000000))
    icon_png = world_dir / "icon.png"
    icon_png.write_bytes(b"\x89PNG\r\n\x1a\n")

    info = WorldManager.read_world_info(world_dir)
    assert info.name == "Super Adventure"
    assert info.folder_name == "MySurvivalWorld"
    assert info.game_mode == "creative"
    assert info.hardcore is False
    assert info.icon_path == str(icon_png)
    assert info.total_size_bytes > 0


def test_world_manager_list_worlds_sorted_by_last_played(tmp_path: Path) -> None:
    saves = tmp_path / "saves"
    saves.mkdir()

    w1 = saves / "WorldOld"
    w1.mkdir()
    (w1 / "level.dat").write_bytes(_build_dummy_level_dat("Old World", last_played=1000000))

    w2 = saves / "WorldNew"
    w2.mkdir()
    (w2 / "level.dat").write_bytes(_build_dummy_level_dat("New World", last_played=9000000))

    worlds = WorldManager.list_worlds(tmp_path)
    assert len(worlds) == 2
    assert worlds[0].name == "New World"
    assert worlds[1].name == "Old World"


def test_world_manager_backup_restore_and_duplicate(tmp_path: Path) -> None:
    saves = tmp_path / "saves"
    saves.mkdir()

    world_dir = saves / "TestWorld"
    world_dir.mkdir()
    (world_dir / "level.dat").write_bytes(_build_dummy_level_dat("Test World"))
    (world_dir / "data.txt").write_text("important save data", encoding="utf-8")

    # Backup
    backup_file = WorldManager.backup_world(tmp_path, "TestWorld")
    assert backup_file.is_file()
    assert backup_file.name.endswith(".zip")

    # Duplicate
    copy_folder = WorldManager.duplicate_world(tmp_path, "TestWorld", "Test World Copy")
    assert (saves / copy_folder).is_dir()
    assert (saves / copy_folder / "data.txt").read_text(encoding="utf-8") == "important save data"

    # Delete original
    WorldManager.delete_world(tmp_path, "TestWorld")
    assert not (saves / "TestWorld").exists()

    # Restore from backup
    restored_folder = WorldManager.restore_world(tmp_path, backup_file)
    assert (saves / restored_folder).is_dir()
    assert (saves / restored_folder / "data.txt").read_text(encoding="utf-8") == "important save data"


def test_world_manager_import_world(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    zip_path = export_dir / "CustomMap.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("CustomMap/level.dat", _build_dummy_level_dat("Custom Map"))
        zf.writestr("CustomMap/map_meta.txt", "map content")

    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()

    imported_folder = WorldManager.import_world(instance_dir, zip_path)
    assert (instance_dir / "saves" / imported_folder).is_dir()
    assert (instance_dir / "saves" / imported_folder / "map_meta.txt").read_text(encoding="utf-8") == "map content"
