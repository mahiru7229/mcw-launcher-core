from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
import json
import os
import shutil
import stat
import zipfile

from src.config import VERSION_TAG
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.models.backup.instance_backup import InstanceBackupInfo, InstanceBackupResult, InstanceRestoreResult
from src.models.instance.instance import Instance


class InstanceBackupManager:
    MANIFEST_NAME = "mcw-backup.json"
    FORMAT_VERSION = 1
    EXTENSION = ".mcwbackup"
    SCOPE_FULL = "full"
    SCOPE_WORLDS = "worlds"
    VALID_SCOPES = {SCOPE_FULL, SCOPE_WORLDS}
    MAX_FILES = 200_000
    MAX_EXTRACT_BYTES = 200 * 1024 * 1024 * 1024
    PROTECTED_ROOTS = {"instance.json", ".mcw", "logs", "crash-reports"}

    @staticmethod
    def create(instance: Instance, scope: str = SCOPE_FULL, reason: str = "manual", destination: Path | None = None) -> InstanceBackupResult:
        normalized_scope = InstanceBackupManager._normalize_scope(scope)
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before creating a backup of this instance.")

        backup_root = Paths.instance_backups_dir(instance)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{InstanceBackupManager._safe_filename(instance.name)}-{normalized_scope}-{timestamp}{InstanceBackupManager.EXTENSION}"
        output = Path(destination) if destination is not None else backup_root / filename
        if output.suffix.lower() != InstanceBackupManager.EXTENSION:
            output = output.with_suffix(InstanceBackupManager.EXTENSION)
        output.parent.mkdir(parents=True, exist_ok=True)

        entries = InstanceBackupManager._collect_files(instance, normalized_scope)
        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "formatVersion": InstanceBackupManager.FORMAT_VERSION,
            "instanceId": instance.instance_id,
            "instanceName": instance.name,
            "scope": normalized_scope,
            "createdAt": created_at,
            "launcherVersion": VERSION_TAG,
            "reason": str(reason or "manual"),
            "fileCount": len(entries),
            "totalSize": sum(path.stat().st_size for _, path in entries),
            "files": [relative.as_posix() for relative, _ in entries],
        }

        temporary = output.with_suffix(output.suffix + ".part")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr(InstanceBackupManager.MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
                for relative, source in entries:
                    archive.write(source, f"payload/{relative.as_posix()}")
            temporary.replace(output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        info = InstanceBackupInfo(path=output, instance_id=instance.instance_id, instance_name=instance.name, scope=normalized_scope, created_at=created_at, file_count=len(entries), total_size=int(manifest["totalSize"]), launcher_version=VERSION_TAG, reason=str(reason or "manual"))
        return InstanceBackupResult(backup=info)

    @staticmethod
    def inspect(path: Path) -> InstanceBackupInfo:
        backup_path = Path(path)
        with zipfile.ZipFile(backup_path, "r") as archive:
            manifest = InstanceBackupManager._read_manifest(archive)
        return InstanceBackupInfo(path=backup_path, instance_id=str(manifest.get("instanceId") or ""), instance_name=str(manifest.get("instanceName") or ""), scope=InstanceBackupManager._normalize_scope(str(manifest.get("scope") or "")), created_at=str(manifest.get("createdAt") or ""), file_count=max(0, int(manifest.get("fileCount", 0) or 0)), total_size=max(0, int(manifest.get("totalSize", 0) or 0)), launcher_version=str(manifest.get("launcherVersion") or ""), reason=str(manifest.get("reason") or "manual"))

    @staticmethod
    def list_backups(instance: Instance) -> list[InstanceBackupInfo]:
        results: list[InstanceBackupInfo] = []
        root = Paths.instance_backups_dir(instance)
        for path in root.glob(f"*{InstanceBackupManager.EXTENSION}"):
            try:
                info = InstanceBackupManager.inspect(path)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                continue
            if info.instance_id in {"", instance.instance_id}:
                results.append(info)
        return sorted(results, key=lambda item: item.created_at, reverse=True)

    @staticmethod
    def restore(instance: Instance, backup_path: Path, create_safety_backup: bool = True) -> InstanceRestoreResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before restoring an instance backup.")

        backup_path = Path(backup_path)
        staging = Paths.backup_staging_root() / uuid4().hex
        rollback = Paths.backup_staging_root() / f"rollback-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        rollback.mkdir(parents=True, exist_ok=False)
        safety_backup: Path | None = None

        try:
            with zipfile.ZipFile(backup_path, "r") as archive:
                manifest = InstanceBackupManager._read_manifest(archive)
                scope = InstanceBackupManager._normalize_scope(str(manifest.get("scope") or ""))
                expected_instance_id = str(manifest.get("instanceId") or "")
                if expected_instance_id and expected_instance_id != instance.instance_id:
                    raise RuntimeError("This backup belongs to a different instance.")
                restored_files = InstanceBackupManager._extract_payload(archive, staging)

            if create_safety_backup:
                safety_backup = InstanceBackupManager.create(instance, InstanceBackupManager.SCOPE_FULL, reason="pre-restore").backup.path

            InstanceBackupManager._apply_payload(instance, staging, rollback, scope)
            return InstanceRestoreResult(instance_name=instance.name, backup_path=backup_path, restored_files=restored_files, scope=scope, safety_backup=safety_backup)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(rollback, ignore_errors=True)

    @staticmethod
    def _apply_payload(instance: Instance, staging: Path, rollback: Path, scope: str) -> None:
        instance_root = Path(instance.instance_dir)
        if scope == InstanceBackupManager.SCOPE_WORLDS:
            targets = ["saves"]
        else:
            targets = sorted({path.name for path in instance_root.iterdir() if path.name not in InstanceBackupManager.PROTECTED_ROOTS} | {path.name for path in staging.iterdir()})

        moved_old: list[str] = []
        installed_new: list[str] = []
        try:
            for name in targets:
                current = instance_root / name
                if current.exists() or current.is_symlink():
                    current.rename(rollback / name)
                    moved_old.append(name)
            for source in staging.iterdir():
                if scope == InstanceBackupManager.SCOPE_WORLDS and source.name != "saves":
                    continue
                target = instance_root / source.name
                InstanceBackupManager._install_staged_path(source, target)
                installed_new.append(source.name)
        except Exception:
            for name in installed_new:
                target = instance_root / name
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            for name in reversed(moved_old):
                source = rollback / name
                if source.exists() or source.is_symlink():
                    source.rename(instance_root / name)
            raise

    @staticmethod
    def _install_staged_path(source: Path, target: Path) -> None:
        try:
            source.rename(target)
            return
        except PermissionError:
            if target.exists() or target.is_symlink():
                raise

        # Windows can deny renaming a recently extracted directory while still
        # allowing its contents to be copied. The staging tree is removed after
        # the complete restore, so a successful copy is equivalent here.
        try:
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        except Exception:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _collect_files(instance: Instance, scope: str) -> list[tuple[PurePosixPath, Path]]:
        root = Path(instance.instance_dir)
        entries: list[tuple[PurePosixPath, Path]] = []
        selected_roots = [root / "saves"] if scope == InstanceBackupManager.SCOPE_WORLDS else [path for path in root.iterdir() if path.name not in InstanceBackupManager.PROTECTED_ROOTS]
        for selected in selected_roots:
            if not selected.exists():
                continue
            if selected.is_file():
                entries.append((PurePosixPath(selected.relative_to(root).as_posix()), selected))
                continue
            for path in selected.rglob("*"):
                if path.is_symlink():
                    continue
                if path.is_file():
                    entries.append((PurePosixPath(path.relative_to(root).as_posix()), path))
                    if len(entries) > InstanceBackupManager.MAX_FILES:
                        raise RuntimeError("The instance contains too many files to back up safely.")
        return sorted(entries, key=lambda item: item[0].as_posix().casefold())

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile) -> dict:
        try:
            raw = archive.read(InstanceBackupManager.MANIFEST_NAME)
        except KeyError as error:
            raise RuntimeError("The backup is missing mcw-backup.json.") from error
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("The backup manifest is invalid.") from error
        if not isinstance(data, dict) or int(data.get("formatVersion", 0) or 0) != InstanceBackupManager.FORMAT_VERSION:
            raise RuntimeError("This MCW backup format is unsupported.")
        InstanceBackupManager._normalize_scope(str(data.get("scope") or ""))
        return data

    @staticmethod
    def _extract_payload(archive: zipfile.ZipFile, staging: Path) -> int:
        total = 0
        count = 0
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith("payload/") or name.endswith("/"):
                continue
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise RuntimeError("Symbolic links are not allowed in MCW backups.")
            relative = InstanceBackupManager._safe_relative(name[len("payload/"):])
            total += int(info.file_size or 0)
            count += 1
            if count > InstanceBackupManager.MAX_FILES or total > InstanceBackupManager.MAX_EXTRACT_BYTES:
                raise RuntimeError("The backup exceeds the configured safety limits.")
            target = staging.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        return count

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath:
        normalized = str(value).replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe path in MCW backup: {value!r}")
        return path

    @staticmethod
    def _normalize_scope(scope: str) -> str:
        normalized = str(scope).strip().lower()
        if normalized not in InstanceBackupManager.VALID_SCOPES:
            raise RuntimeError(f"Unsupported backup scope: {scope!r}")
        return normalized

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = "".join(character if character.isalnum() or character in {" ", "-", "_", "."} else "_" for character in str(value)).strip(" .")
        return cleaned or "instance"
