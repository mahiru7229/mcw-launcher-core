from src.models.minecraft.version import Version
from src.models.instance.instance import Instance
from src.models.progress.progress_callback import ProgressCallback
from src.models.instance.settings import InstanceSettings
from src.models.package.instance_package_preview import InstancePackagePreview
from src.core.config.launcher_settings_manager import LauncherSettingsManager
from src.core.fs.atomic_file import atomic_write_text
from src.core.fs.paths import Paths
from src.core.instance.settings_manager import SettingsManager
from src.core.instance.instance_deletion_manager import InstanceDeletionManager
from src.core.instance.instance_operation_journal import InstanceOperationJournal
from src.core.package.package_manager import PackageManager
from src.config import VERSION_TAG

from pathlib import Path
from datetime import datetime, timezone
import json
import os
import re
import shutil
import time
import uuid


class InstanceManager:
    METADATA_VERSION = 3
    DEFAULT_ICON = "grass_block"
    ICON_DIRECTORY = ".mcw"
    ICON_BASENAME = "instance-icon"
    ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".ico"}
    MAX_ICON_BYTES = 8 * 1024 * 1024
    DIRECTORY_COMMIT_ATTEMPTS = 8
    DIRECTORY_COMMIT_RETRY_SECONDS = 0.15
    INSTANCE_NAME_PATTERN = re.compile(r'^[^<>:"/\\|?*\x00-\x1F]{1,80}$')
    WINDOWS_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}

    @staticmethod
    def validate_name(value: str) -> str:
        name = str(value).strip()
        device_name = name.split(".", 1)[0].casefold()
        if not name or name in {".", ".."} or name.endswith((" ", ".")) or not InstanceManager.INSTANCE_NAME_PATTERN.fullmatch(name) or device_name in InstanceManager.WINDOWS_RESERVED_NAMES:
            raise RuntimeError("The instance name is not valid on Windows.")
        return name

    @staticmethod
    def _save_instance_metadata(instance: Instance) -> None:
        instance_dir = Path(instance.instance_dir)
        path = instance_dir / "instance.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}

        now = datetime.now(timezone.utc).isoformat()
        created_at = str(existing.get("created_at") or now)
        last_played = str(instance.last_played or existing.get("last_played") or "")
        last_exit_code = instance.last_exit_code if instance.last_exit_code is not None else existing.get("last_exit_code")
        last_launch_crashed = bool(instance.last_launch_crashed)
        requested_state = str(getattr(instance, "last_launch_state", "") or "").strip().casefold()
        existing_state = str(existing.get("last_launch_state") or "").strip().casefold()
        inferred_state = "crashed" if last_launch_crashed else "finished" if last_played else "ready"
        if requested_state in {"finished", "crashed"}:
            last_launch_state = requested_state
        elif requested_state == "ready" and not last_played:
            last_launch_state = "ready"
        elif existing_state in {"ready", "finished", "crashed"}:
            last_launch_state = existing_state
        else:
            last_launch_state = inferred_state
        data = dict(existing)
        data.update({
            "id": instance.instance_id,
            "name": instance.name,
            "version_id": instance.version_id,
            "mod_loader": instance.mod_loader,
            "instance_dir": str(instance_dir),
            "created_at": created_at,
            "updated_at": now,
            "last_played": last_played,
            "last_exit_code": last_exit_code,
            "last_launch_crashed": last_launch_crashed,
            "last_launch_state": last_launch_state,
            "last_started_at": str(existing.get("last_started_at") or ""),
            "last_finished_at": str(existing.get("last_finished_at") or ""),
            "icon": str(instance.icon or existing.get("icon") or InstanceManager.DEFAULT_ICON),
            "notes": str(existing.get("notes") or ""),
            "favorite": bool(getattr(instance, "favorite", existing.get("favorite", False))),
            "group": str(getattr(instance, "group", existing.get("group", "")) or "").strip(),
            "tags": list(InstanceManager._normalize_tags(getattr(instance, "tags", existing.get("tags", ())))),
            "launcher_version": VERSION_TAG,
            "metadata_version": InstanceManager.METADATA_VERSION,
        })

        atomic_write_text(path, json.dumps(data, indent=4, ensure_ascii=False) + "\n")

    @staticmethod
    def _update_instance_metadata_fields(instance: Instance, updates: dict) -> None:
        path = Path(instance.instance_dir) / "instance.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise RuntimeError(f"Invalid instance metadata: {path}") from error
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid instance metadata: {path}")
        data.update(dict(updates))
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write_text(path, json.dumps(data, indent=4, ensure_ascii=False) + "\n")

    @staticmethod
    def _load_instance_metadata(path: Path) -> Instance:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid instance metadata: {path}") from error
        return InstanceManager._parse_instance_metadata(data, path.parent, path)

    @staticmethod
    def _parse_instance_metadata(data: object, instance_dir: Path, source: object = "instance.json") -> Instance:
        try:
            if not isinstance(data, dict):
                raise ValueError("instance.json must contain an object.")
            instance_id = str(data["id"]).strip()
            name = str(data["name"]).strip()
            version_id = str(data["version_id"]).strip()
            raw_loader = data.get("mod_loader", ("vanilla", "-1"))
            if not instance_id or not name or not version_id or not isinstance(raw_loader, (list, tuple)) or len(raw_loader) != 2:
                raise ValueError("instance.json is missing required fields.")
            mod_loader = (str(raw_loader[0]).strip().lower() or "vanilla", str(raw_loader[1]).strip() or "-1")
            icon = str(data.get("icon") or InstanceManager.DEFAULT_ICON).strip() or InstanceManager.DEFAULT_ICON
            last_played = str(data.get("last_played") or "")
            raw_exit_code = data.get("last_exit_code")
            last_exit_code = int(raw_exit_code) if raw_exit_code is not None else None
            last_launch_crashed = bool(data.get("last_launch_crashed", False))
            raw_state = str(data.get("last_launch_state") or "").strip().casefold()
            inferred_state = "crashed" if last_launch_crashed else "finished" if last_played else "ready"
            last_launch_state = raw_state if raw_state in {"ready", "finished", "crashed"} else inferred_state
            favorite = bool(data.get("favorite", False))
            group = str(data.get("group") or "").strip()
            tags = InstanceManager._normalize_tags(data.get("tags", ()))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid instance metadata: {source}") from error
        return Instance(
            instance_id=instance_id,
            name=name,
            version_id=version_id,
            mod_loader=mod_loader,
            instance_dir=instance_dir,
            icon=icon,
            last_played=last_played,
            last_exit_code=last_exit_code,
            last_launch_crashed=last_launch_crashed,
            last_launch_state=last_launch_state,
            favorite=favorite,
            group=group,
            tags=tags,
        )

    @staticmethod
    def _normalize_tags(values: object) -> tuple[str, ...]:
        if isinstance(values, str):
            values = values.split(",")
        if not isinstance(values, (list, tuple, set)):
            return ()
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            tag = str(value or "").strip()
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            result.append(tag)
        return tuple(result)

    @staticmethod
    def set_library_metadata(name: str, *, favorite: bool | None = None, group: str | None = None, tags: object | None = None) -> Instance:
        instance = InstanceManager.load(name)
        if favorite is not None:
            instance.favorite = bool(favorite)
        if group is not None:
            instance.group = str(group or "").strip()
        if tags is not None:
            instance.tags = InstanceManager._normalize_tags(tags)
        InstanceManager._save_instance_metadata(instance)
        return InstanceManager.load(name)

    @staticmethod
    def list_instances() -> list[Instance]:
        instances: list[Instance] = []
        deleted_names = InstanceDeletionManager.process_pending()
        if deleted_names:
            deleted = {name.casefold() for name in deleted_names}
            instances_data = InstanceManager._load_instances_data()
            instances_data["instances"] = [
                item for item in instances_data.get("instances", [])
                if str(item.get("name") or "").casefold() not in deleted
            ]
            InstanceManager._save_instances(instances_data)

        root = Paths.instances_root()

        for instance_dir in root.iterdir():
            if not instance_dir.is_dir():
                continue

            metadata_path = instance_dir / "instance.json"

            if not metadata_path.exists():
                continue

            try:
                instance = InstanceManager.load(instance_dir.name)
            except RuntimeError:
                continue
            instances.append(instance)

        return instances

    @staticmethod
    def clone(source_name: str, new_name: str, include_saves: bool = False) -> Instance:
        new_name = InstanceManager.validate_name(new_name)
        if not InstanceManager.is_instance_exist(source_name):
            raise RuntimeError(f"Instance '{source_name}' does not exist.")
        if InstanceManager.is_instance_exist(new_name):
            raise RuntimeError(f"Instance '{new_name}' already exists.")

        source_dir = Paths.load_instance_dir(source_name)
        target_dir = Paths.load_instance_dir(new_name)
        staging_dir = Paths.instance_staging_root() / f"clone-{uuid.uuid4().hex}"
        journal = InstanceOperationJournal.begin("clone", new_name, source_path=source_dir, target_path=target_dir, staging_path=staging_dir)
        committed = False
        ignore = None if include_saves else shutil.ignore_patterns("saves", "logs", "crash-reports")

        try:
            shutil.copytree(source_dir, staging_dir, ignore=ignore)
            InstanceManager._reset_cloned_runtime_data(staging_dir)
            instance = InstanceManager._load_instance_metadata(staging_dir / "instance.json")
            instance.instance_id = str(uuid.uuid4())
            instance.name = new_name
            instance.instance_dir = staging_dir
            InstanceManager._save_instance_metadata(instance)

            journal.update("committing")
            InstanceManager._commit_staging_directory(staging_dir, target_dir)
            committed = True
            instance.instance_dir = target_dir
            InstanceManager._save_instance_metadata(instance)
            InstanceManager.reconcile_registry()
            journal.complete()
            return InstanceManager.load(new_name)
        except Exception:
            rollback_target = target_dir if committed else staging_dir
            try:
                if rollback_target.exists():
                    shutil.rmtree(rollback_target)
                InstanceManager.reconcile_registry()
                journal.abandon()
            except OSError:
                pass
            raise


    @staticmethod
    def _reset_cloned_runtime_data(instance_dir: Path) -> None:
        metadata_path = instance_dir / "instance.json"
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            data = {}
        if isinstance(data, dict):
            data.update({
                "last_played": "",
                "total_play_time_seconds": 0,
                "last_exit_code": None,
                "last_launch_crashed": False,
                "last_launch_state": "ready",
                "last_started_at": "",
                "last_finished_at": "",
                "last_game_log": "",
                "last_crash_report": "",
            })
            temporary = metadata_path.with_name(f"{metadata_path.name}.tmp")
            temporary.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(metadata_path)
        mcw_dir = instance_dir / ".mcw"
        for filename in ("runtime-history.json", "last-repair.json"):
            try:
                (mcw_dir / filename).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def export(instance_name: str, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path:
        instance = InstanceManager.load(instance_name)

        return PackageManager.export_instance(instance, output_path, include_saves, on_progress)

    @staticmethod
    def set_icon(instance_name: str, source_path: Path, origin: dict | None = None) -> Instance:
        instance = InstanceManager.load(instance_name)
        source = Path(source_path).expanduser()
        if not source.is_file():
            raise RuntimeError("The selected instance icon does not exist.")
        extension = source.suffix.casefold()
        if extension not in InstanceManager.ICON_EXTENSIONS:
            raise RuntimeError("Unsupported instance icon format.")
        try:
            size = source.stat().st_size
        except OSError as error:
            raise RuntimeError("The selected instance icon cannot be read.") from error
        if size <= 0 or size > InstanceManager.MAX_ICON_BYTES:
            raise RuntimeError("Instance icons must be between 1 byte and 8 MiB.")

        icon_dir = Path(instance.instance_dir) / InstanceManager.ICON_DIRECTORY
        icon_dir.mkdir(parents=True, exist_ok=True)
        target = icon_dir / f"{InstanceManager.ICON_BASENAME}{extension}"
        temporary = target.with_name(f".{target.name}.tmp")
        source_resolved = source.resolve()
        target_resolved = target.resolve(strict=False)
        if source_resolved != target_resolved:
            try:
                with source.open("rb") as input_file, temporary.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                    output_file.flush()
                    os.fsync(output_file.fileno())
                temporary.replace(target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise

        for old_icon in icon_dir.glob(f"{InstanceManager.ICON_BASENAME}.*"):
            if old_icon != target:
                old_icon.unlink(missing_ok=True)

        instance.icon = target.relative_to(instance.instance_dir).as_posix()
        InstanceManager._save_instance_metadata(instance)
        normalized_origin = dict(origin) if isinstance(origin, dict) else {"provider": "custom"}
        normalized_origin["provider"] = str(normalized_origin.get("provider") or "custom").strip().casefold() or "custom"
        InstanceManager._update_instance_metadata_fields(instance, {"icon_origin": normalized_origin})
        return InstanceManager.load(instance.name)

    @staticmethod
    def reset_icon(instance_name: str) -> Instance:
        instance = InstanceManager.load(instance_name)
        icon_dir = Path(instance.instance_dir) / InstanceManager.ICON_DIRECTORY
        for old_icon in icon_dir.glob(f"{InstanceManager.ICON_BASENAME}.*"):
            old_icon.unlink(missing_ok=True)
        instance.icon = InstanceManager.DEFAULT_ICON
        InstanceManager._save_instance_metadata(instance)
        InstanceManager._update_instance_metadata_fields(instance, {"icon_origin": {"provider": "default"}})
        return InstanceManager.load(instance.name)

    @staticmethod
    def resolve_icon_path(instance: Instance) -> Path | None:
        value = str(instance.icon or "").strip()
        if not value or value == InstanceManager.DEFAULT_ICON:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = Path(instance.instance_dir) / path
        return path if path.is_file() else None

    @staticmethod
    def inspect_import(package_path: Path) -> InstancePackagePreview:
        metadata, instance_data, settings_data = PackageManager.inspect_instance(Path(package_path))
        instance = InstanceManager._parse_instance_metadata(instance_data, Path(), package_path)
        instance.name = InstanceManager.validate_name(instance.name)
        if InstanceManager.is_instance_exist(instance.name):
            raise RuntimeError(f"Instance '{instance.name}' already exists.")
        return InstancePackagePreview(
            package_path=Path(package_path),
            name=instance.name,
            version_id=instance.version_id,
            mod_loader=instance.mod_loader,
            icon=instance.icon,
            settings=SettingsManager.normalize_dict(settings_data),
            has_package_settings=settings_data is not None,
            package_metadata=metadata,
        )

    @staticmethod
    def import_instance(
        package_path: Path,
        on_progress: ProgressCallback | None = None,
        settings_override: dict | InstanceSettings | None = None,
    ) -> Instance:
        staging_dir = Paths.instance_staging_root() / f"import-{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        journal: InstanceOperationJournal | None = None
        target_dir: Path | None = None
        committed = False

        try:
            PackageManager.extract(package_path, staging_dir, on_progress)
            metadata_files = list(staging_dir.rglob("instance.json"))
            if len(metadata_files) != 1:
                raise RuntimeError("Invalid package: missing or duplicated instance.json.")

            metadata_path = metadata_files[0]
            imported_dir = metadata_path.parent
            instance = InstanceManager._load_instance_metadata(metadata_path)
            instance.name = InstanceManager.validate_name(instance.name)
            if InstanceManager.is_instance_exist(instance.name):
                raise RuntimeError(f"Instance '{instance.name}' already exists.")

            instance.name, target_dir = InstanceManager._resolve_import_target(instance.name)
            journal = InstanceOperationJournal.begin("import", instance.name, target_path=target_dir, staging_path=staging_dir)
            if settings_override is not None:
                SettingsManager.save_dict(instance, settings_override)
            elif (imported_dir / "settings.json").is_file():
                SettingsManager.save(instance, SettingsManager.load(instance))
            else:
                SettingsManager.save_dict(instance, InstanceManager.default_instance_settings())

            if imported_dir != staging_dir:
                normalized_staging = staging_dir.with_name(f"{staging_dir.name}-instance")
                if normalized_staging.exists():
                    shutil.rmtree(normalized_staging)
                imported_dir.rename(normalized_staging)
                shutil.rmtree(staging_dir)
                staging_dir = normalized_staging
                journal.update("prepared", staging_path=str(staging_dir))

            instance.instance_dir = staging_dir
            InstanceManager._save_instance_metadata(instance)
            journal.update("committing")
            InstanceManager._commit_staging_directory(staging_dir, target_dir, allow_copy_fallback=True)
            committed = True
            instance.instance_dir = target_dir
            InstanceManager._save_instance_metadata(instance)
            InstanceManager.reconcile_registry()
            journal.complete()
            return InstanceManager.load(instance.name)
        except Exception:
            rollback_target = target_dir if committed and target_dir is not None else staging_dir
            try:
                if rollback_target.exists():
                    shutil.rmtree(rollback_target)
                InstanceManager.reconcile_registry()
                if journal is not None:
                    journal.abandon()
            except OSError:
                pass
            raise


    @staticmethod
    def _resolve_import_target(preferred_name: str) -> tuple[str, Path]:
        name = InstanceManager.validate_name(preferred_name)
        target = Paths.load_instance_dir(name)
        if not target.exists():
            return name, target

        # A valid instance remains a hard conflict. An orphan directory is never
        # overwritten or deleted silently; choose a deterministic free name.
        if (target / "instance.json").is_file() or InstanceManager._find_instance_data(name) is not None:
            raise RuntimeError(f"Instance '{name}' already exists.")

        alternate = InstanceManager.next_available_name(name)
        return alternate, Paths.load_instance_dir(alternate)

    @staticmethod
    def _commit_staging_directory(staging_dir: Path, target_dir: Path, *, allow_copy_fallback: bool = False) -> None:
        if target_dir.exists():
            raise RuntimeError(f"Cannot commit instance because the target directory already exists: {target_dir}")

        last_error: OSError | None = None
        for attempt in range(InstanceManager.DIRECTORY_COMMIT_ATTEMPTS):
            try:
                staging_dir.rename(target_dir)
                return
            except FileExistsError as error:
                raise RuntimeError(f"Cannot commit instance because the target directory already exists: {target_dir}") from error
            except PermissionError as error:
                last_error = error
            except OSError as error:
                if getattr(error, "winerror", None) not in {5, 32, 33}:
                    raise
                last_error = error

            if target_dir.exists():
                raise RuntimeError(f"Cannot commit instance because the target directory became occupied: {target_dir}") from last_error
            if not staging_dir.exists():
                raise RuntimeError(f"Cannot commit instance because the staging directory disappeared: {staging_dir}") from last_error
            if attempt + 1 < InstanceManager.DIRECTORY_COMMIT_ATTEMPTS:
                time.sleep(InstanceManager.DIRECTORY_COMMIT_RETRY_SECONDS * (attempt + 1))

        if allow_copy_fallback:
            InstanceManager._commit_staging_directory_by_copy(staging_dir, target_dir)
            return

        raise RuntimeError(
            f"Windows could not finalize the instance operation after {InstanceManager.DIRECTORY_COMMIT_ATTEMPTS} attempts. "
            f"Staging: {staging_dir}; target: {target_dir}. Close programs scanning these folders and retry."
        ) from last_error

    @staticmethod
    def _commit_staging_directory_by_copy(staging_dir: Path, target_dir: Path) -> None:
        """Publish an imported instance without renaming a directory containing scanned JARs.

        Windows security/indexing tools may temporarily open a nested JAR without
        FILE_SHARE_DELETE. That blocks renaming the *parent* staging directory even
        though every file remains readable. Copying into a fresh target avoids that
        Windows-only restriction. ``instance.json`` is copied last, so the instance
        cannot become visible to the launcher until every other file is present.
        """
        metadata_source = staging_dir / "instance.json"
        if not staging_dir.is_dir() or not metadata_source.is_file():
            raise RuntimeError(f"Cannot copy-commit an incomplete instance staging directory: {staging_dir}")
        if target_dir.exists():
            raise RuntimeError(f"Cannot commit instance because the target directory already exists: {target_dir}")

        marker = target_dir / ".mcw-import-incomplete"
        published = False
        try:
            target_dir.mkdir(parents=False, exist_ok=False)
            marker.write_text("MCW instance import is still being committed.\n", encoding="utf-8")

            for root, directory_names, file_names in os.walk(staging_dir, topdown=True, followlinks=False):
                source_root = Path(root)
                relative_root = source_root.relative_to(staging_dir)
                destination_root = target_dir / relative_root
                destination_root.mkdir(parents=True, exist_ok=True)

                for directory_name in list(directory_names):
                    source_directory = source_root / directory_name
                    if source_directory.is_symlink():
                        raise RuntimeError(f"Cannot safely copy-commit a symbolic-link directory: {source_directory}")
                    (destination_root / directory_name).mkdir(parents=True, exist_ok=True)

                for file_name in file_names:
                    source_file = source_root / file_name
                    relative_file = source_file.relative_to(staging_dir)
                    if relative_file == Path("instance.json"):
                        continue
                    if source_file.is_symlink():
                        raise RuntimeError(f"Cannot safely copy-commit a symbolic-link file: {source_file}")
                    InstanceManager._copy_commit_file(source_file, target_dir / relative_file)

            metadata_temporary = target_dir / f".instance.json.{uuid.uuid4().hex}.tmp"
            InstanceManager._copy_commit_file(metadata_source, metadata_temporary)
            metadata_temporary.replace(target_dir / "instance.json")
            published = True
            marker.unlink(missing_ok=True)
        except Exception:
            if not published:
                try:
                    (target_dir / "instance.json").unlink(missing_ok=True)
                except OSError:
                    pass
                shutil.rmtree(target_dir, ignore_errors=True)
            raise
        finally:
            if published:
                InstanceManager._remove_committed_staging_best_effort(staging_dir)

    @staticmethod
    def _copy_commit_file(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: OSError | None = None

        for attempt in range(InstanceManager.DIRECTORY_COMMIT_ATTEMPTS):
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
            try:
                with source.open("rb") as input_file, temporary.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                    output_file.flush()
                    os.fsync(output_file.fileno())
                temporary.replace(destination)
                return
            except PermissionError as error:
                last_error = error
            except OSError as error:
                if getattr(error, "winerror", None) not in {5, 32, 33}:
                    temporary.unlink(missing_ok=True)
                    raise
                last_error = error
            finally:
                temporary.unlink(missing_ok=True)

            if attempt + 1 < InstanceManager.DIRECTORY_COMMIT_ATTEMPTS:
                time.sleep(InstanceManager.DIRECTORY_COMMIT_RETRY_SECONDS * (attempt + 1))

        raise RuntimeError(f"Windows could not copy an imported instance file after repeated attempts: {source}") from last_error

    @staticmethod
    def _remove_committed_staging_best_effort(staging_dir: Path) -> None:
        for attempt in range(InstanceManager.DIRECTORY_COMMIT_ATTEMPTS):
            try:
                shutil.rmtree(staging_dir)
                return
            except FileNotFoundError:
                return
            except OSError:
                if attempt + 1 < InstanceManager.DIRECTORY_COMMIT_ATTEMPTS:
                    time.sleep(InstanceManager.DIRECTORY_COMMIT_RETRY_SECONDS * (attempt + 1))
        # StartupRecoveryManager removes orphan staging directories on the next run.


    @staticmethod
    def rename(instance_name: str, new_name: str) -> Path:
        new_name = InstanceManager.validate_name(new_name)
        if not InstanceManager.is_instance_exist(instance_name):
            raise RuntimeError(f"Instance '{instance_name}' does not exist!")
        if InstanceManager.is_instance_exist(new_name):
            raise RuntimeError(f"Instance '{new_name}' already exists!")
        if instance_name == new_name:
            return Paths.load_instance_dir(instance_name)

        old_dir = Paths.load_instance_dir(instance_name)
        new_dir = Paths.load_instance_dir(new_name)
        journal = InstanceOperationJournal.begin("rename", new_name, source_path=old_dir, target_path=new_dir)
        moved = False

        try:
            journal.update("committing")
            old_dir.rename(new_dir)
            moved = True
            instance = InstanceManager._load_instance_metadata(new_dir / "instance.json")
            instance.name = new_name
            instance.instance_dir = new_dir
            InstanceManager._save_instance_metadata(instance)
            InstanceManager.reconcile_registry()
            journal.complete()
            return new_dir
        except Exception:
            rollback_succeeded = False
            if moved and new_dir.exists() and not old_dir.exists():
                try:
                    new_dir.rename(old_dir)
                    instance = InstanceManager._load_instance_metadata(old_dir / "instance.json")
                    instance.name = instance_name
                    instance.instance_dir = old_dir
                    InstanceManager._save_instance_metadata(instance)
                    InstanceManager.reconcile_registry()
                    rollback_succeeded = True
                except Exception:
                    rollback_succeeded = False
            elif not moved:
                rollback_succeeded = True
            if rollback_succeeded:
                journal.abandon()
            raise


    @staticmethod
    def load(name: str) -> Instance:
        instance_dir = Paths.load_instance_dir(name)
        metadata_path = instance_dir / "instance.json"

        if metadata_path.exists():
            instance = InstanceManager._load_instance_metadata(metadata_path)
            repaired = False

            if instance.name != name:
                instance.name = name
                repaired = True

            if Path(instance.instance_dir) != instance_dir:
                instance.instance_dir = instance_dir
                repaired = True

            if repaired:
                InstanceManager._save_instance_metadata(instance)

            return instance

        instance_data = InstanceManager._find_instance_data(name)

        if instance_data is None:
            raise RuntimeError(
                f"Instance '{name}' not found."
            )

        instance = InstanceManager._parse_instance(instance_data)
        instance.name = name
        instance.instance_dir = instance_dir

        InstanceManager._migrate_instance(instance)

        return instance

    @staticmethod
    def _migrate_instance(instance: Instance) -> None:
        InstanceManager._save_instance_metadata(instance)

    @staticmethod
    def create(
        name: str,
        version: Version,
        mod_loader=("vanilla", "-1"),
        settings: dict | InstanceSettings | None = None,
    ) -> Instance:
        name = InstanceManager.validate_name(name)
        if InstanceManager.is_instance_exist(name):
            raise RuntimeError(f"Instance '{name}' already exists.")

        target_dir = Paths.load_instance_dir(name)
        staging_dir = Paths.instance_staging_root() / f"create-{uuid.uuid4().hex}"
        journal = InstanceOperationJournal.begin("create", name, target_path=target_dir, staging_path=staging_dir)
        committed = False

        try:
            staging_dir.mkdir(parents=True, exist_ok=False)
            instance = InstanceManager._add_instance(name, version, mod_loader)
            instance.instance_dir = staging_dir
            InstanceManager._save_instance_metadata(instance)
            SettingsManager.save_dict(instance, settings if settings is not None else InstanceManager.default_instance_settings())

            journal.update("committing")
            InstanceManager._commit_staging_directory(staging_dir, target_dir)
            committed = True
            instance.instance_dir = target_dir
            InstanceManager._save_instance_metadata(instance)
            InstanceManager.reconcile_registry()
            journal.complete()
            return InstanceManager.load(name)
        except Exception:
            rollback_target = target_dir if committed else staging_dir
            try:
                if rollback_target.exists():
                    shutil.rmtree(rollback_target)
                InstanceManager.reconcile_registry()
                journal.abandon()
            except OSError:
                pass
            raise


    @staticmethod
    def default_instance_settings() -> dict:
        try:
            settings = LauncherSettingsManager().load().get("instance_defaults")
        except (OSError, RuntimeError, TypeError, ValueError):
            settings = None
        return SettingsManager.normalize_dict(settings)

    @staticmethod
    def set_runtime_profile(name: str, version: Version, mod_loader: tuple[str, str]) -> Instance:
        instance = InstanceManager.load(name)
        normalized_loader = (str(mod_loader[0]).strip().lower(), str(mod_loader[1]).strip())
        if normalized_loader[0] == "vanilla":
            normalized_loader = ("vanilla", "-1")
        instance.version_id = version.id
        instance.mod_loader = normalized_loader
        InstanceManager._save_instance_metadata(instance)
        instances_data = InstanceManager._load_instances_data()
        for item in instances_data.get("instances", []):
            if item.get("name") == name:
                item["version_id"] = version.id
                item["mod_loader"] = normalized_loader
                item["instance_dir"] = str(instance.instance_dir)
                break
        InstanceManager._save_instances(instances_data)
        return instance

    @staticmethod
    def set_mod_loader(name: str, mod_loader: tuple[str, str]) -> Instance:
        instance = InstanceManager.load(name)
        normalized_loader = (str(mod_loader[0]).strip().lower(), str(mod_loader[1]).strip())

        if normalized_loader[0] == "vanilla":
            normalized_loader = ("vanilla", "-1")

        instance.mod_loader = normalized_loader
        InstanceManager._save_instance_metadata(instance)

        instances_data = InstanceManager._load_instances_data()
        for item in instances_data.get("instances", []):
            if item.get("name") == name:
                item["mod_loader"] = normalized_loader
                break
        InstanceManager._save_instances(instances_data)
        return instance

    @staticmethod
    def delete_instance(name: str) -> bool:
        if not InstanceManager.is_instance_exist(name):
            return False

        instance = InstanceManager.load(name)
        InstanceDeletionManager.delete(instance)

        Paths.instances_root()
        Paths.instance_data_path_create()
        instances_data = InstanceManager._load_instances_data()
        instances_data["instances"] = [
            item for item in instances_data.get("instances", [])
            if item.get("name") != name
        ]
        InstanceManager._save_instances(instances_data)
        return True

    @staticmethod
    def reconcile_registry() -> dict:
        entries: list[dict] = []
        root = Paths.instances_root()
        for instance_dir in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            if not instance_dir.is_dir() or instance_dir.name.startswith("."):
                continue
            metadata_path = instance_dir / "instance.json"
            if not metadata_path.is_file():
                continue
            try:
                instance = InstanceManager.load(instance_dir.name)
            except RuntimeError:
                continue
            entries.append({
                "id": instance.instance_id,
                "name": instance.name,
                "version_id": instance.version_id,
                "mod_loader": instance.mod_loader,
                "instance_dir": str(instance.instance_dir),
            })
        data = {"instances": entries}
        InstanceManager._save_instances(data)
        return data

    @staticmethod
    def next_available_name(preferred_name: str) -> str:
        base_name = InstanceManager.validate_name(str(preferred_name).strip() or "New Instance")
        try:
            existing_names = {instance.name.casefold() for instance in InstanceManager.list_instances()}
        except Exception:
            existing_names = set()

        def is_taken(candidate: str) -> bool:
            return candidate.casefold() in existing_names or Paths.load_instance_dir(candidate).exists() or InstanceManager.is_instance_exist(candidate)

        if not is_taken(base_name):
            return base_name
        suffix = 2
        while True:
            candidate = f"{base_name} ({suffix})"
            if not is_taken(candidate):
                return candidate
            suffix += 1

    @staticmethod
    def is_instance_exist(name: str) -> bool:
        metadata_path = Paths.instance_metadata(name)

        if metadata_path.exists():
            return True

        return InstanceManager._find_instance_data(name) is not None

    @staticmethod
    def _find_instance_data(name: str) -> dict | None:
        instances_data = InstanceManager._load_instances_data()

        for instance in instances_data.get("instances", []):
            if instance.get("name") == name:
                return instance

        return None

    @staticmethod
    def _add_instance(
        name: str,
        version: Version,
        mod_loader: tuple
    ) -> Instance:
        return Instance(
            instance_id=str(uuid.uuid4()),
            name=name,
            version_id=version.id,
            mod_loader=mod_loader,
            instance_dir=Paths.load_instance_dir(name)
        )

    @staticmethod
    def _parse_instance(instance_data: dict) -> Instance:
        return Instance(
            instance_id=instance_data.get("id")
            or instance_data.get("instance_id")
            or str(uuid.uuid4()),
            name=instance_data.get("name"),
            version_id=instance_data.get("version_id"),
            mod_loader=instance_data.get("mod_loader"),
            instance_dir=Paths.load_instance_dir(instance_data.get("name")),
            icon=str(instance_data.get("icon") or InstanceManager.DEFAULT_ICON),
            last_played=str(instance_data.get("last_played") or ""),
            last_exit_code=instance_data.get("last_exit_code"),
            last_launch_crashed=bool(instance_data.get("last_launch_crashed", False)),
            last_launch_state=str(instance_data.get("last_launch_state") or ("crashed" if instance_data.get("last_launch_crashed") else "finished" if instance_data.get("last_played") else "ready")),
            favorite=bool(instance_data.get("favorite", False)),
            group=str(instance_data.get("group") or "").strip(),
            tags=InstanceManager._normalize_tags(instance_data.get("tags", ())),
        )

    @staticmethod
    def _load_instances_data() -> dict:
        try:
            data = json.loads(Paths.instance_data_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return {"instances": []}
        if not isinstance(data, dict) or not isinstance(data.get("instances", []), list):
            return {"instances": []}
        return data

    @staticmethod
    def _add_instances_data(
        pre_data: dict,
        instance_data: Instance
    ) -> dict:
        if "instances" not in pre_data:
            pre_data["instances"] = []

        pre_data["instances"].append(
            {
                "id": instance_data.instance_id,
                "name": instance_data.name,
                "version_id": instance_data.version_id,
                "mod_loader": instance_data.mod_loader,
                "instance_dir": str(instance_data.instance_dir)
            }
        )

        return pre_data

    @staticmethod
    def _save_instances(data: dict) -> Path:
        instance_data_path = Paths.instance_data_path()
        instance_data_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(instance_data_path, json.dumps(data, indent=4, ensure_ascii=False) + "\n")
        return instance_data_path
