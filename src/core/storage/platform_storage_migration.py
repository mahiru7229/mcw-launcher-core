from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from src.core.fs.atomic_file import atomic_write_text
from src.core.fs.paths import Paths


@dataclass(frozen=True, slots=True)
class PlatformStorageMigrationReport:
    copied_files: int = 0
    copied_bytes: int = 0
    skipped_files: int = 0
    conflicts: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    already_completed: bool = False

    @property
    def completed(self) -> bool:
        return not self.errors


class PlatformStorageMigration:
    """Copy Alpha 2's portable Linux data into XDG roots without deleting it."""

    SCHEMA_VERSION = 1
    MARKER_NAME = ".platform-storage-migration-v1.json"

    @classmethod
    def migrate(cls, legacy_root: Path | str | None = None) -> PlatformStorageMigrationReport:
        source_root = Path(legacy_root or Paths.PROJECT_ROOT).expanduser().resolve(strict=False)
        marker = Paths.CONFIG_ROOT / cls.MARKER_NAME
        if cls._completed_marker(marker):
            return PlatformStorageMigrationReport(already_completed=True)
        if not Paths.uses_platform_storage():
            return PlatformStorageMigrationReport(already_completed=True)

        mappings = (
            (source_root / "config", Paths.CONFIG_ROOT),
            (source_root / "cache", Paths.CACHE_ROOT),
            (source_root / "instances", Paths.INSTANCES_ROOT),
            (source_root / "accounts", Paths.ACCOUNTS_ROOT),
            (source_root / "logs", Paths.LOGS_ROOT),
            (source_root / "backups", Paths.BACKUPS_ROOT),
            (source_root / "themes", Paths.THEME_ROOT),
            (source_root / "runtimes", Paths.RUNTIMES_ROOT),
        )

        copied_files = 0
        copied_bytes = 0
        skipped_files = 0
        conflicts: list[str] = []
        errors: list[str] = []

        for source, destination in mappings:
            if not source.is_dir() or source.resolve(strict=False) == destination.resolve(strict=False):
                continue
            try:
                candidates = tuple(sorted(source.rglob("*"), key=lambda path: path.as_posix().casefold()))
            except OSError as error:
                errors.append(f"{source}: {type(error).__name__}")
                continue

            for candidate in candidates:
                if candidate.is_symlink():
                    try:
                        relative = candidate.relative_to(source)
                        target = destination / relative
                        link_target = cls._validated_link_target(candidate, source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists() or target.is_symlink():
                            if target.is_symlink() and os.readlink(target) == link_target:
                                skipped_files += 1
                            else:
                                conflicts.append(target.as_posix())
                            continue
                        cls._copy_symlink_atomic(link_target, target)
                        copied_files += 1
                    except (OSError, ValueError) as error:
                        errors.append(f"{candidate}: {error}")
                    continue
                if not candidate.is_file():
                    continue
                try:
                    relative = candidate.relative_to(source)
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        if cls._same_file(candidate, target):
                            skipped_files += 1
                        else:
                            conflicts.append(target.as_posix())
                        continue
                    size = candidate.stat().st_size
                    cls._copy_atomic(candidate, target)
                    copied_files += 1
                    copied_bytes += max(0, int(size))
                except OSError as error:
                    errors.append(f"{candidate}: {type(error).__name__}")

        report = PlatformStorageMigrationReport(
            copied_files=copied_files,
            copied_bytes=copied_bytes,
            skipped_files=skipped_files,
            conflicts=tuple(conflicts),
            errors=tuple(errors),
        )
        cls._write_marker(marker, source_root, report)
        return report

    @staticmethod
    def _copy_atomic(source: Path, destination: Path) -> None:
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary, follow_symlinks=False)
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validated_link_target(link: Path, source_root: Path) -> str:
        raw_target = os.readlink(link)
        if not raw_target or os.path.isabs(raw_target):
            raise ValueError("absolute or empty symbolic link target is not migrated")
        source_boundary = source_root.resolve(strict=False)
        resolved_target = (link.parent / raw_target).resolve(strict=False)
        if not resolved_target.is_relative_to(source_boundary):
            raise ValueError("symbolic link target escapes the migration source")
        return raw_target

    @staticmethod
    def _copy_symlink_atomic(link_target: str, destination: Path) -> None:
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temporary.symlink_to(link_target)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _same_file(left: Path, right: Path) -> bool:
        try:
            if left.stat().st_size != right.stat().st_size:
                return False
            return PlatformStorageMigration._sha256(left) == PlatformStorageMigration._sha256(right)
        except OSError:
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _completed_marker(cls, path: Path) -> bool:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return False
        return (
            isinstance(payload, dict)
            and payload.get("schemaVersion") == cls.SCHEMA_VERSION
            and payload.get("complete") is True
        )

    @classmethod
    def _write_marker(cls, path: Path, source_root: Path, report: PlatformStorageMigrationReport) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": cls.SCHEMA_VERSION,
            "complete": report.completed,
            "legacyRoot": str(source_root),
            "legacyDataPreserved": True,
            "report": asdict(report),
        }
        atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


platform_storage_migration = PlatformStorageMigration()
