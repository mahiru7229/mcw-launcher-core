from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
import json
import os
import stat
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from src.config import LAUNCHER_SLUG, VERSION_TAG
from src.core.fs.paths import Paths
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.package.package_metadata import PackageMetadata
from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_stage import ProgressStage


class PackageManager:
    FORMAT = "mcwpack"
    FORMAT_VERSION = 1
    PACKAGE_TYPE_INSTANCE = "instance"
    MAX_ARCHIVE_FILES = 500_000
    MAX_EXTRACTED_BYTES = 128 * 1024 * 1024 * 1024
    MAX_METADATA_BYTES = 1024 * 1024
    COPY_CHUNK_SIZE = 1024 * 1024
    WINDOWS_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}
    WINDOWS_INVALID_CHARACTERS = set('<>:"|?*')

    LAUNCHER_NAME = LAUNCHER_SLUG
    LAUNCHER_VERSION = VERSION_TAG

    @staticmethod
    def create_instance_package_metadata(include_saves: bool, instance: Instance | None = None, icon: str = "") -> PackageMetadata:
        return PackageMetadata(
            format=PackageManager.FORMAT,
            format_version=PackageManager.FORMAT_VERSION,
            package_type=PackageManager.PACKAGE_TYPE_INSTANCE,
            launcher_name=PackageManager.LAUNCHER_NAME,
            launcher_version=PackageManager.LAUNCHER_VERSION,
            created_at=datetime.now(UTC).isoformat(),
            include_saves=include_saves,
            instance_name=str(getattr(instance, "name", "") or ""),
            instance_icon=str(icon or getattr(instance, "icon", "") or ""),
        )

    @staticmethod
    def package_metadata_to_dict(metadata: PackageMetadata) -> dict:
        return {
            "format": metadata.format,
            "format_version": metadata.format_version,
            "package_type": metadata.package_type,
            "launcher_name": metadata.launcher_name,
            "launcher_version": metadata.launcher_version,
            "created_at": metadata.created_at,
            "include_saves": metadata.include_saves,
            "instance_name": metadata.instance_name,
            "instance_icon": metadata.instance_icon,
        }

    @staticmethod
    def load_package_metadata(archive: ZipFile) -> PackageMetadata:
        if "package.json" not in archive.namelist():
            raise RuntimeError("Invalid package: missing package.json.")
        try:
            data = json.loads(archive.read("package.json").decode("utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("package.json must contain an object.")
            return PackageMetadata(
                format=data["format"],
                format_version=int(data["format_version"]),
                package_type=data["package_type"],
                launcher_name=data["launcher_name"],
                launcher_version=data["launcher_version"],
                created_at=data["created_at"],
                include_saves=bool(data["include_saves"]),
                instance_name=str(data.get("instance_name") or ""),
                instance_icon=str(data.get("instance_icon") or ""),
            )
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Invalid package: package.json is malformed.") from error

    @staticmethod
    def validate_package(metadata: PackageMetadata) -> None:
        if metadata.format != PackageManager.FORMAT:
            raise RuntimeError("Invalid package format.")
        if metadata.format_version > PackageManager.FORMAT_VERSION:
            raise RuntimeError("Package was created by a newer launcher.")
        if metadata.package_type != PackageManager.PACKAGE_TYPE_INSTANCE:
            raise RuntimeError("Package is not an instance package.")

    @staticmethod
    def export_instance(instance: Instance, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path:
        instance_dir = Paths.load_instance_dir(instance.name)
        if not instance_dir.exists():
            raise RuntimeError(f"Instance directory '{instance_dir}' does not exist.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() != ".mcwpack":
            output_path = output_path.with_suffix(".mcwpack")

        reporter = ProgressReporter(on_progress)
        reporter.status(stage=ProgressStage.EXPORTING_INSTANCE, message=f"Scanning files for '{instance.name}'...")
        temporary_path = output_path.with_name(f".{output_path.name}.part")
        files = PackageManager._collect_export_files(instance_dir, include_saves, {output_path.resolve(), temporary_path.resolve()})
        files, file_overrides, exported_icon = PackageManager._prepare_instance_icon_export(instance, instance_dir, files)
        metadata = PackageManager.create_instance_package_metadata(include_saves, instance=instance, icon=exported_icon)
        metadata_bytes = (json.dumps(PackageManager.package_metadata_to_dict(metadata), indent=4, ensure_ascii=False) + "\n").encode("utf-8")
        total_bytes = len(metadata_bytes) + sum(len(file_overrides.get(relative, b"")) if relative in file_overrides else size for _, relative, size in files)
        processed_bytes = 0

        reporter.bytes(stage=ProgressStage.EXPORTING_INSTANCE, message=f"Exporting '{instance.name}'...", current=0, total=total_bytes)
        try:
            temporary_path.unlink(missing_ok=True)
            with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
                archive.writestr("package.json", metadata_bytes)
                processed_bytes += len(metadata_bytes)
                reporter.bytes(stage=ProgressStage.EXPORTING_INSTANCE, message="Exporting package metadata...", current=processed_bytes, total=total_bytes)

                for source_path, relative_path, _size in files:
                    override = file_overrides.get(relative_path)
                    if override is not None:
                        archive.writestr(relative_path.as_posix(), override)
                        processed_bytes += len(override)
                        reporter.bytes(stage=ProgressStage.EXPORTING_INSTANCE, message=f"Exporting {relative_path.as_posix()}...", current=min(processed_bytes, total_bytes), total=total_bytes)
                        continue
                    with source_path.open("rb") as source, archive.open(relative_path.as_posix(), "w", force_zip64=True) as destination:
                        while chunk := source.read(PackageManager.COPY_CHUNK_SIZE):
                            destination.write(chunk)
                            processed_bytes += len(chunk)
                            reporter.bytes(stage=ProgressStage.EXPORTING_INSTANCE, message=f"Exporting {relative_path.as_posix()}...", current=min(processed_bytes, total_bytes), total=total_bytes)

            with temporary_path.open("r+b") as package_file:
                os.fsync(package_file.fileno())
            temporary_path.replace(output_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        reporter.bytes(stage=ProgressStage.EXPORTING_INSTANCE, message=f"Export completed for '{instance.name}'.", current=total_bytes, total=total_bytes)
        return output_path

    @staticmethod
    def extract(package_path: Path, output_dir: Path, on_progress: ProgressCallback | None = None) -> PackageMetadata:
        if not package_path.exists():
            raise RuntimeError(f"Package '{package_path}' does not exist.")
        if package_path.suffix.lower() != ".mcwpack":
            raise RuntimeError("Invalid package extension.")

        output_dir.mkdir(parents=True, exist_ok=True)
        reporter = ProgressReporter(on_progress)
        reporter.status(stage=ProgressStage.IMPORTING_INSTANCE, message=f"Reading '{package_path.name}'...")
        try:
            with ZipFile(package_path, "r") as archive:
                metadata = PackageManager.load_package_metadata(archive)
                PackageManager.validate_package(metadata)
                PackageManager._extract_archive(archive, output_dir, reporter)
                return metadata
        except BadZipFile as error:
            raise RuntimeError("Invalid package: the archive is corrupted.") from error

    @staticmethod
    def inspect_instance(package_path: Path) -> tuple[PackageMetadata, dict, dict | None]:
        if not package_path.exists():
            raise RuntimeError(f"Package '{package_path}' does not exist.")
        if package_path.suffix.lower() != ".mcwpack":
            raise RuntimeError("Invalid package extension.")

        inspection_root = package_path.parent / ".mcwpack-inspection"
        try:
            with ZipFile(package_path, "r") as archive:
                metadata = PackageManager.load_package_metadata(archive)
                PackageManager.validate_package(metadata)
                members, _total_bytes = PackageManager._validated_members(archive, inspection_root)
                instance_members = [
                    (member, relative)
                    for member, relative, _target in members
                    if not member.is_dir() and relative.name.casefold() == "instance.json"
                ]
                if len(instance_members) != 1:
                    raise RuntimeError("Invalid package: missing or duplicated instance.json.")

                instance_member, instance_relative = instance_members[0]
                instance_data = PackageManager._read_json_member(archive, instance_member, "instance.json")
                settings_relative = instance_relative.parent / "settings.json"
                settings_members = [
                    member
                    for member, relative, _target in members
                    if not member.is_dir() and relative.as_posix().casefold() == settings_relative.as_posix().casefold()
                ]
                if len(settings_members) > 1:
                    raise RuntimeError("Invalid package: duplicated settings.json.")
                settings_data = (
                    PackageManager._read_json_member(archive, settings_members[0], "settings.json")
                    if settings_members
                    else None
                )
                return metadata, instance_data, settings_data
        except BadZipFile as error:
            raise RuntimeError("Invalid package: the archive is corrupted.") from error

    @staticmethod
    def _read_json_member(archive: ZipFile, member: ZipInfo, label: str) -> dict:
        if int(member.file_size or 0) > PackageManager.MAX_METADATA_BYTES:
            raise RuntimeError(f"Invalid package: {label} is too large.")
        try:
            raw = archive.read(member)
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid package: {label} is malformed.") from error
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid package: {label} must contain an object.")
        return data

    @staticmethod
    def _prepare_instance_icon_export(instance: Instance, instance_dir: Path, files: list[tuple[Path, PurePosixPath, int]]) -> tuple[list[tuple[Path, PurePosixPath, int]], dict[PurePosixPath, bytes], str]:
        icon_value = str(getattr(instance, "icon", "") or "grass_block").strip() or "grass_block"
        icon_path = Path(icon_value)
        if not icon_path.is_absolute():
            candidate = instance_dir / icon_path
            if candidate.is_file():
                return files, {}, icon_path.as_posix()
            return files, {}, icon_value
        if not icon_path.is_file():
            return files, {}, "grass_block"
        try:
            icon_path.resolve().relative_to(instance_dir.resolve())
            relative_icon = PurePosixPath(icon_path.resolve().relative_to(instance_dir.resolve()).as_posix())
            return files, {}, relative_icon.as_posix()
        except ValueError:
            pass

        extension = icon_path.suffix.casefold() if icon_path.suffix else ".png"
        archive_icon = PurePosixPath(f".mcw/instance-icon{extension}")
        filtered = [item for item in files if item[1] != archive_icon]
        filtered.append((icon_path, archive_icon, max(0, icon_path.stat().st_size)))
        filtered.sort(key=lambda item: item[1].as_posix().casefold())

        metadata_path = instance_dir / "instance.json"
        try:
            instance_data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            instance_data = {}
        overrides: dict[PurePosixPath, bytes] = {}
        if isinstance(instance_data, dict):
            instance_data["icon"] = archive_icon.as_posix()
            overrides[PurePosixPath("instance.json")] = (json.dumps(instance_data, indent=4, ensure_ascii=False) + "\n").encode("utf-8")
        return filtered, overrides, archive_icon.as_posix()

    @staticmethod
    def _collect_export_files(instance_dir: Path, include_saves: bool, excluded_paths: set[Path]) -> list[tuple[Path, PurePosixPath, int]]:
        files: list[tuple[Path, PurePosixPath, int]] = []
        for path in instance_dir.rglob("*"):
            if path.is_dir() or path.is_symlink():
                continue
            resolved_path = path.resolve()
            if resolved_path in excluded_paths:
                continue
            relative = PurePosixPath(path.relative_to(instance_dir).as_posix())
            if not include_saves and relative.parts and relative.parts[0].casefold() == "saves":
                continue
            files.append((path, relative, max(0, path.stat().st_size)))
        files.sort(key=lambda item: item[1].as_posix().casefold())
        return files

    @staticmethod
    def _extract_archive(archive: ZipFile, output_dir: Path, reporter: ProgressReporter) -> None:
        members, total_bytes = PackageManager._validated_members(archive, output_dir)
        processed_bytes = 0
        reporter.bytes(stage=ProgressStage.IMPORTING_INSTANCE, message="Importing package files...", current=0, total=total_bytes)

        for member, relative, target in members:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as destination:
                while chunk := source.read(PackageManager.COPY_CHUNK_SIZE):
                    destination.write(chunk)
                    processed_bytes += len(chunk)
                    reporter.bytes(stage=ProgressStage.IMPORTING_INSTANCE, message=f"Importing {relative.as_posix()}...", current=min(processed_bytes, total_bytes), total=total_bytes)

        reporter.bytes(stage=ProgressStage.IMPORTING_INSTANCE, message="Package files imported.", current=total_bytes, total=total_bytes)

    @staticmethod
    def _validated_members(archive: ZipFile, output_dir: Path) -> tuple[list[tuple[ZipInfo, PurePosixPath, Path]], int]:
        members: list[tuple[ZipInfo, PurePosixPath, Path]] = []
        extracted_bytes = 0
        extracted_files = 0
        seen_paths: dict[str, ZipInfo] = {}
        output_root = output_dir.resolve()

        for member in archive.infolist():
            if PackageManager._is_symlink(member):
                raise RuntimeError(f"Invalid package: symbolic links are not allowed ({member.filename}).")

            relative = PackageManager._safe_relative_path(member.filename)
            if relative is None:
                continue

            path_key = relative.as_posix().casefold()
            previous = seen_paths.get(path_key)
            if previous is not None:
                if PackageManager._duplicate_members_match(previous, member):
                    continue
                raise RuntimeError(f"Invalid package: conflicting duplicate path '{relative.as_posix()}'.")
            seen_paths[path_key] = member

            target = output_dir.joinpath(*relative.parts)
            resolved_target = target.resolve(strict=False)
            if not resolved_target.is_relative_to(output_root):
                raise RuntimeError(f"Invalid package path: {member.filename!r}.")

            if not member.is_dir():
                extracted_files += 1
                extracted_bytes += max(0, int(member.file_size or 0))
                if extracted_files > PackageManager.MAX_ARCHIVE_FILES:
                    raise RuntimeError("Invalid package: too many files.")
                if extracted_bytes > PackageManager.MAX_EXTRACTED_BYTES:
                    raise RuntimeError("Invalid package: extracted data exceeds the safety limit.")

            members.append((member, relative, target))

        return members, extracted_bytes

    @staticmethod
    def _duplicate_members_match(first: ZipInfo, second: ZipInfo) -> bool:
        if first.is_dir() and second.is_dir():
            return True
        if first.is_dir() != second.is_dir():
            return False
        return int(first.file_size or 0) == int(second.file_size or 0) and int(first.CRC or 0) == int(second.CRC or 0)

    @staticmethod
    def _safe_relative_path(value: str) -> PurePosixPath | None:
        normalized = str(value).replace("\\", "/").strip()
        if not normalized:
            return None
        path = PurePosixPath(normalized)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Invalid package path: {value!r}.")
        if not path.parts or "\x00" in normalized:
            raise RuntimeError(f"Invalid package path: {value!r}.")
        for part in path.parts:
            device_name = part.split(".", 1)[0].casefold()
            if part.endswith((" ", ".")) or device_name in PackageManager.WINDOWS_RESERVED_NAMES or any(character in PackageManager.WINDOWS_INVALID_CHARACTERS or ord(character) < 32 for character in part):
                raise RuntimeError(f"Invalid Windows package path: {value!r}.")
        return path

    @staticmethod
    def _is_symlink(member: ZipInfo) -> bool:
        return stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF)
