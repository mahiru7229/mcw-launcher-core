from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import shutil
import zipfile

from src.core.backup.instance_backup_manager import InstanceBackupManager
from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_pack_installer import ModrinthPackInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_pack_update_manager import ModrinthPackUpdateManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.pack_repair import ModrinthPackRepairResult
from src.models.progress.progress_stage import ProgressStage


class ModrinthPackRepairManager:
    @staticmethod
    def repair(instance: Instance, reporter: ProgressReporter | None = None) -> ModrinthPackRepairResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before repairing this modpack.")

        registry = ModrinthPackRegistry.load(instance)
        project_id = str(registry.get("projectId") or "").strip()
        version_id = str(registry.get("versionId") or "").strip()
        if not project_id or not version_id:
            raise RuntimeError("This instance is not managed by a Modrinth modpack.")

        project = ModrinthClient.get_project(project_id)
        version = ModrinthClient.get_version(version_id, force_refresh=True)
        if version.project_id != project_id:
            raise RuntimeError("The saved Modrinth modpack version no longer belongs to this project.")
        pack_file = version.primary_file(".mrpack")
        pack_path = Paths.modrinth_pack_cache(project_id, version_id, pack_file.filename)
        ModrinthDownloader.download_file(pack_file, pack_path, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODPACK, progress_message=f"Downloading {project.title} repair manifest...")

        staging = Paths.modrinth_staging_root() / f"repair-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        previous_profile = (instance.version_id, tuple(instance.mod_loader))
        backup_path: Path | None = None

        try:
            root = Path(instance.instance_dir)
            with zipfile.ZipFile(pack_path, "r") as archive:
                index = ModrinthPackInstaller._read_index(archive)
                minecraft_version, loader_name, loader_version = ModrinthPackInstaller._parse_dependencies(index)
                selected_files, _, _ = ModrinthPackInstaller._selected_files(index, bool(registry.get("installOptionalFiles", True)))
                managed_files = {entry["path"].casefold(): entry for entry in ModrinthPackInstaller._managed_download_entries(selected_files)}
                for entry in ModrinthPackInstaller._extract_layer(archive, "overrides", staging):
                    managed_files[entry["path"].casefold()] = entry
                for entry in ModrinthPackInstaller._extract_layer(archive, "client-overrides", staging):
                    managed_files[entry["path"].casefold()] = entry

            current_loader = ModrinthPackUpdateManager._registry_loader(registry)
            if loader_name != current_loader:
                raise RuntimeError(f"The saved pack expects {current_loader.title()}, but its manifest now declares {loader_name.title()}.")

            base_version = VersionManager.load(minecraft_version)
            resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
            ModLoaderManager.prepare(base_version, *resolved_loader, reporter=reporter)

            cache = ModrinthPackRegistry._normalize_verification_cache(registry.get("verificationCache", {}), registry.get("managedFiles", []))
            changed: list[tuple[str, dict, str]] = []
            healthy = 0
            total = len(managed_files)
            ModrinthPackRepairManager._report(reporter, ProgressStage.CHECKING_MODPACK, "Verifying managed modpack files for repair...", 0, total)
            for completed, (key, entry) in enumerate(managed_files.items(), start=1):
                relative = ModrinthPackRegistry._safe_relative(str(entry.get("path") or ""))
                if relative is None:
                    raise RuntimeError(f"Unsafe managed Modrinth path: {entry.get('path')!r}")
                target = root.joinpath(*relative.parts)
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=cache, force_hash=True)
                if verified:
                    healthy += 1
                else:
                    changed.append((key, entry, "modified" if target.exists() else "missing"))
                ModrinthPackRepairManager._report(reporter, ProgressStage.CHECKING_MODPACK, "Verifying managed modpack files for repair...", completed, total)

            selected_by_path = {str(item.get("path") or "").replace("\\", "/").casefold(): item for item in selected_files}
            pending_downloads = [selected_by_path[key] for key, entry, _state in changed if str(entry.get("source") or "") == "download" and key in selected_by_path]
            if reporter is None:
                ModrinthPackInstaller._download_files(pending_downloads, staging)
            else:
                ModrinthPackInstaller._download_files(pending_downloads, staging, reporter)

            if changed:
                backup_path = InstanceBackupManager.create(instance, InstanceBackupManager.SCOPE_FULL, reason="pre-modpack-repair").backup.path

            restored: list[str] = []
            missing_count = sum(1 for _key, _entry, state in changed if state == "missing")
            modified_count = sum(1 for _key, _entry, state in changed if state == "modified")
            ModrinthPackRepairManager._report(reporter, ProgressStage.REPAIRING_INSTANCE, "Restoring managed modpack files...", 0, len(changed))
            for completed, (_key, entry, _state) in enumerate(changed, start=1):
                relative = ModrinthPackUpdateManager._relative(str(entry.get("path") or ""))
                source = staging.joinpath(*relative.parts)
                target = root.joinpath(*relative.parts)
                if not source.is_file():
                    raise RuntimeError(f"The repair source is missing: {relative.as_posix()}")
                ModrinthPackRepairManager._atomic_copy(source, target)
                restored.append(relative.as_posix())
                ModrinthPackRepairManager._report(reporter, ProgressStage.REPAIRING_INSTANCE, "Restoring managed modpack files...", completed, len(changed))

            updated = InstanceManager.set_runtime_profile(instance.name, base_version, resolved_loader)
            managed_list = list(managed_files.values())
            managed_keys = set(managed_files)
            preserved = [item for item in registry.get("preservedFiles", []) if isinstance(item, dict) and str(item.get("path") or "").casefold() not in managed_keys]
            verification_cache = ModrinthPackRegistry.build_verification_cache(updated.instance_dir, managed_list)
            payload = {
                "projectId": project_id,
                "versionId": version.version_id,
                "name": project.title,
                "versionNumber": version.version_number,
                "versionType": version.version_type,
                "datePublished": version.date_published,
                "minecraftVersion": minecraft_version,
                "loader": loader_name,
                "loaderVersion": loader_version,
                "installOptionalFiles": bool(registry.get("installOptionalFiles", True)),
                "managedFiles": managed_list,
                "preservedFiles": preserved,
                "verificationCache": verification_cache,
                "lastRepair": datetime.now(timezone.utc).isoformat(),
            }
            if backup_path is not None:
                payload["lastBackup"] = str(backup_path)
            elif registry.get("lastBackup"):
                payload["lastBackup"] = str(registry.get("lastBackup"))
            ModrinthPackRegistry.save(updated.instance_dir, payload)
            return ModrinthPackRepairResult(instance_name=instance.name, pack_name=project.title, pack_version=version.version_number, restored_files=tuple(sorted(restored)), missing_files=missing_count, modified_files=modified_count, healthy_files=healthy, backup_path=backup_path)
        except Exception as error:
            if backup_path is not None:
                try:
                    InstanceBackupManager.restore(instance, backup_path, create_safety_backup=False)
                    old_version = VersionManager.load(previous_profile[0])
                    InstanceManager.set_runtime_profile(instance.name, old_version, previous_profile[1])
                    ModrinthPackRegistry.save(instance.instance_dir, registry)
                except Exception as rollback_error:
                    raise RuntimeError(f"Modpack repair failed and rollback also failed: {rollback_error}") from error
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _atomic_copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".repair.part")
        temp.unlink(missing_ok=True)
        shutil.copy2(source, temp)
        temp.replace(target)

    @staticmethod
    def _report(reporter: ProgressReporter | None, stage: ProgressStage, message: str, current: int, total: int) -> None:
        if reporter is not None:
            reporter.files(stage=stage, message=message, current=current, total=total)
