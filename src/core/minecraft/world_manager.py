from __future__ import annotations

from datetime import datetime, timezone
import gzip
from pathlib import Path
import re
import shutil
import struct
import zipfile

from src.models.world.world_info import WorldInfo


class WorldManager:
    """Manages singleplayer saves, NBT metadata extraction, backup, and restore."""

    GAME_MODES = {
        0: "survival",
        1: "creative",
        2: "adventure",
        3: "spectator",
    }

    @classmethod
    def list_worlds(cls, instance_dir: Path | str) -> list[WorldInfo]:
        saves_dir = Path(instance_dir) / "saves"
        if not saves_dir.is_dir():
            return []

        worlds: list[WorldInfo] = []
        for folder in saves_dir.iterdir():
            if not folder.is_dir():
                continue
            # Skip hidden or temporary folders
            if folder.name.startswith((".", "_")):
                continue
            world = cls.read_world(folder)
            if world is not None:
                worlds.append(world)

        # Sort by last played descending (most recently played first)
        worlds.sort(key=lambda w: w.last_played, reverse=True)
        return worlds

    @classmethod
    def read_world(cls, folder: Path) -> WorldInfo | None:
        level_dat = folder / "level.dat"
        mtime = 0.0
        try:
            mtime = folder.stat().st_mtime
        except OSError:
            pass

        data = {}
        if level_dat.is_file():
            try:
                mtime = level_dat.stat().st_mtime
                data = cls.parse_level_dat(level_dat)
            except Exception:
                data = {}

        level_data = data.get("Data", data) if isinstance(data, dict) else {}
        display_name = str(level_data.get("LevelName") or folder.name)
        game_type = level_data.get("GameType", 0)
        game_mode = cls.GAME_MODES.get(game_type, "survival")
        is_hardcore = bool(level_data.get("hardcore", 0))
        if is_hardcore:
            game_mode = "hardcore"

        last_played = int(level_data.get("LastPlayed") or int(mtime * 1000))
        version_data = level_data.get("Version")
        version_name = ""
        if isinstance(version_data, dict):
            version_name = str(version_data.get("Name") or "")

        icon_file = folder / "icon.png"
        icon_path = str(icon_file) if icon_file.is_file() else ""

        # Approximate size
        size_bytes = 0
        try:
            for item in folder.rglob("*"):
                if item.is_file():
                    size_bytes += item.stat().st_size
        except OSError:
            pass

        return WorldInfo(
            folder_name=folder.name,
            display_name=display_name,
            game_mode=game_mode,
            is_hardcore=is_hardcore,
            last_played=last_played,
            version_name=version_name,
            folder_size_bytes=size_bytes,
            icon_path=icon_path,
            folder_path=folder,
        )

    read_world_info = read_world

    @classmethod
    def parse_level_dat(cls, path: Path) -> dict:
        try:
            content = path.read_bytes()
        except OSError:
            return {}
        if not content:
            return {}
        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except Exception:
                return {}

        offset = 0

        def read_string() -> str:
            nonlocal offset
            if offset + 2 > len(content):
                return ""
            (str_len,) = struct.unpack_from(">H", content, offset)
            offset += 2
            if offset + str_len > len(content):
                offset = len(content)
                return ""
            s = content[offset : offset + str_len].decode("utf-8", errors="replace")
            offset += str_len
            return s

        def parse_tag(tag_type: int):
            nonlocal offset
            if tag_type == 1:  # Byte
                if offset >= len(content):
                    return 0
                v = struct.unpack_from(">b", content, offset)[0]
                offset += 1
                return v
            elif tag_type == 2:  # Short
                if offset + 2 > len(content):
                    return 0
                v = struct.unpack_from(">h", content, offset)[0]
                offset += 2
                return v
            elif tag_type == 3:  # Int
                if offset + 4 > len(content):
                    return 0
                v = struct.unpack_from(">i", content, offset)[0]
                offset += 4
                return v
            elif tag_type == 4:  # Long
                if offset + 8 > len(content):
                    return 0
                v = struct.unpack_from(">q", content, offset)[0]
                offset += 8
                return v
            elif tag_type == 5:  # Float
                if offset + 4 > len(content):
                    return 0.0
                v = struct.unpack_from(">f", content, offset)[0]
                offset += 4
                return v
            elif tag_type == 6:  # Double
                if offset + 8 > len(content):
                    return 0.0
                v = struct.unpack_from(">d", content, offset)[0]
                offset += 8
                return v
            elif tag_type == 7:  # Byte Array
                if offset + 4 > len(content):
                    return b""
                (arr_len,) = struct.unpack_from(">i", content, offset)
                offset += 4 + max(0, arr_len)
                return None
            elif tag_type == 8:  # String
                return read_string()
            elif tag_type == 9:  # List
                if offset + 5 > len(content):
                    return []
                sub_type = content[offset]
                (list_len,) = struct.unpack_from(">i", content, offset + 1)
                offset += 5
                items = []
                for _ in range(min(max(0, list_len), 10000)):
                    if offset >= len(content):
                        break
                    items.append(parse_tag(sub_type))
                return items
            elif tag_type == 10:  # Compound
                result = {}
                while offset < len(content):
                    t = content[offset]
                    offset += 1
                    if t == 0:  # End
                        break
                    name = read_string()
                    result[name] = parse_tag(t)
                return result
            elif tag_type == 11:  # Int Array
                if offset + 4 > len(content):
                    return None
                (arr_len,) = struct.unpack_from(">i", content, offset)
                offset += 4 + max(0, arr_len) * 4
                return None
            elif tag_type == 12:  # Long Array
                if offset + 4 > len(content):
                    return None
                (arr_len,) = struct.unpack_from(">i", content, offset)
                offset += 4 + max(0, arr_len) * 8
                return None
            return None

        if len(content) < 3 or content[0] != 10:
            return {}
        offset = 1
        _ = read_string()  # root name
        res = parse_tag(10)
        return res if isinstance(res, dict) else {}

    @classmethod
    def backup_world(
        cls, instance_dir: Path | str, world_folder: str, target_dir: Path | str | None = None
    ) -> Path:
        source = Path(instance_dir) / "saves" / world_folder
        if not source.is_dir():
            raise FileNotFoundError(f"World folder '{world_folder}' does not exist.")

        out_dir = Path(target_dir) if target_dir is not None else Path(instance_dir) / "backups"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        sanitized = re.sub(r"[^\w\-.]", "_", world_folder)
        archive_name = f"world_{sanitized}_{timestamp}.zip"
        archive_path = out_dir / archive_name

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in source.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source.parent)
                    zip_file.write(file_path, arcname)

        return archive_path

    @classmethod
    def restore_world(cls, instance_dir: Path | str, backup_path: Path | str) -> str:
        """Restores a world from a backup zip archive into instance saves."""
        return cls.import_world(instance_dir, backup_path)

    @classmethod
    def duplicate_world(cls, instance_dir: Path | str, world_folder: str, new_name: str = "") -> str:
        saves_dir = Path(instance_dir) / "saves"
        source = saves_dir / world_folder
        if not source.is_dir():
            raise FileNotFoundError(f"World folder '{world_folder}' does not exist.")

        if not new_name:
            counter = 1
            while True:
                candidate = f"{world_folder} (Copy {counter})" if counter > 1 else f"{world_folder} (Copy)"
                if not (saves_dir / candidate).exists():
                    target_name = candidate
                    break
                counter += 1
        else:
            target_name = new_name

        target = saves_dir / target_name
        shutil.copytree(source, target)
        return target_name

    @classmethod
    def delete_world(cls, instance_dir: Path | str, world_folder: str) -> bool:
        source = Path(instance_dir) / "saves" / world_folder
        if not source.is_dir():
            return False
        shutil.rmtree(source)
        return True

    @classmethod
    def import_world(cls, instance_dir: Path | str, source_path: Path | str) -> str:
        source = Path(source_path)
        saves_dir = Path(instance_dir) / "saves"
        saves_dir.mkdir(parents=True, exist_ok=True)

        if source.is_dir():
            target_name = source.name
            target = saves_dir / target_name
            if target.exists():
                counter = 1
                while (saves_dir / f"{target_name} ({counter})").exists():
                    counter += 1
                target = saves_dir / f"{target_name} ({counter})"
            shutil.copytree(source, target)
            return target.name

        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source, "r") as archive:
                namelist = archive.namelist()
                # Determine top-level folder inside zip
                top_members = [name for name in namelist if not name.startswith("__MACOSX")]
                level_dat_members = [name for name in top_members if name.endswith("level.dat")]
                if level_dat_members:
                    # Found level.dat
                    level_path = level_dat_members[0]
                    folder_prefix = str(Path(level_path).parent).replace("\\", "/")
                    if folder_prefix in ("", "."):
                        # Files are directly in archive root
                        target_name = source.stem
                    else:
                        target_name = Path(folder_prefix).name
                else:
                    target_name = source.stem

                target_dir = saves_dir / target_name
                counter = 1
                while target_dir.exists():
                    target_dir = saves_dir / f"{target_name} ({counter})"
                    counter += 1
                target_dir.mkdir(parents=True, exist_ok=True)

                if level_dat_members and str(Path(level_dat_members[0]).parent).replace("\\", "/") not in ("", "."):
                    prefix = str(Path(level_dat_members[0]).parent).replace("\\", "/") + "/"
                    for member in archive.infolist():
                        if member.filename.startswith(prefix) and not member.is_dir():
                            rel = member.filename[len(prefix) :]
                            dest = target_dir / rel
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(member) as s_file, open(dest, "wb") as d_file:
                                shutil.copyfileobj(s_file, d_file)
                else:
                    archive.extractall(target_dir)

                return target_dir.name

        raise ValueError(f"Source '{source_path}' is neither a folder nor a zip archive.")
