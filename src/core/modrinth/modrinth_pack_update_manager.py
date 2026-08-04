from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib
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
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.pack_update import (
    ModrinthPackUpdateChange,
    ModrinthPackUpdateInfo,
    ModrinthPackUpdatePlan,
    ModrinthPackUpdateResult,
)
from src.models.progress.progress_stage import ProgressStage


class ModrinthPackUpdateManager:
    @staticmethod
    def check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateInfo | None:
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.loading_registry", 0, 5)
        registry = ModrinthPackRegistry.load(instance)
        project_id = str(registry.get("projectId") or "").strip()
        current_version_id = str(registry.get("versionId") or "").strip()
        if not project_id or not current_version_id:
            if reporter is not None:
                reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.not_managed", 5, 5)
            return None
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.loading_project", 1, 5)
        project = ModrinthClient.get_project(project_id, force_refresh=force_refresh)
        current_number = str(registry.get("versionNumber") or current_version_id)
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.loading_current", 2, 5)
        try:
            current_version = ModrinthClient.get_version(current_version_id, force_refresh=force_refresh)
            current_timestamp = ModrinthClient._published_timestamp(current_version.date_published)
            current_number = current_version.version_number
        except RuntimeError:
            current_timestamp = 0.0
        loader_name = ModrinthPackUpdateManager._registry_loader(registry)
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.loading_versions", 3, 5)
        versions = ModrinthClient.list_project_versions(project_id, loader=loader_name, game_version=str(registry.get("minecraftVersion") or instance.version_id), version_types=allowed_version_types, force_refresh=force_refresh)
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.comparing", 4, 5)
        candidate = next((version for version in versions if version.version_id != current_version_id and ModrinthClient._published_timestamp(version.date_published) > current_timestamp), None)
        if reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODPACK, "modpack.update_check.checked", 5, 5)
        if candidate is None:
            return ModrinthPackUpdateInfo(project_id=project_id, pack_name=project.title, current_version_id=current_version_id, current_version_number=current_number, target_version_id="", target_version_number="", target_version_type="", target_date_published="")
        return ModrinthPackUpdateInfo(project_id=project_id, pack_name=project.title, current_version_id=current_version_id, current_version_number=current_number, target_version_id=candidate.version_id, target_version_number=candidate.version_number, target_version_type=candidate.version_type, target_date_published=candidate.date_published)

    @staticmethod
    def preview(instance: Instance, target_version_id: str = "", allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdatePlan:
        registry = ModrinthPackRegistry.load(instance)
        project_id = str(registry.get("projectId") or "").strip()
        current_version_id = str(registry.get("versionId") or "").strip()
        if not project_id or not current_version_id:
            raise RuntimeError("This instance is not managed by a Modrinth modpack.")

        target_id = str(target_version_id or "").strip()
        if not target_id:
            update_info = ModrinthPackUpdateManager.check(instance, allowed_version_types, force_refresh=True, reporter=reporter)
            if update_info is None or not update_info.available:
                raise RuntimeError("This Modrinth modpack is already up to date.")
            target_id = update_info.target_version_id

        project = ModrinthClient.get_project(project_id)
        target_version = ModrinthClient.get_version(target_id, force_refresh=True)
        if target_version.project_id != project_id:
            raise RuntimeError("The selected update does not belong to this Modrinth modpack.")
        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        if target_version.version_type not in allowed_types:
            raise RuntimeError(f"The selected modpack update uses the disabled {target_version.version_type} channel.")

        pack_file = target_version.primary_file(".mrpack")
        pack_path = Paths.modrinth_pack_cache(project_id, target_version.version_id, pack_file.filename)
        if reporter is None:
            ModrinthDownloader.download_file(pack_file, pack_path)
        else:
            ModrinthDownloader.download_file(
                pack_file,
                pack_path,
                reporter=reporter,
                progress_stage=ProgressStage.DOWNLOADING_MODPACK,
                progress_message=f"Downloading {project.title} update preview...",
            )

        staging = Paths.modrinth_staging_root() / f"update-preview-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(pack_path, "r") as archive:
                index = ModrinthPackInstaller._read_index(archive)
                minecraft_version, loader_name, loader_version = ModrinthPackInstaller._parse_dependencies(index)
                selected_files, _, _ = ModrinthPackInstaller._selected_files(index, bool(registry.get("installOptionalFiles", True)))
                managed_files = {
                    entry["path"].casefold(): entry
                    for entry in ModrinthPackInstaller._managed_download_entries(selected_files)
                }
                for entry in ModrinthPackInstaller._extract_layer(archive, "overrides", staging):
                    managed_files[entry["path"].casefold()] = entry
                for entry in ModrinthPackInstaller._extract_layer(archive, "client-overrides", staging):
                    managed_files[entry["path"].casefold()] = entry

            blockers: list[str] = []
            current_loader = ModrinthPackUpdateManager._registry_loader(registry)
            if loader_name != current_loader:
                blockers.append(
                    f"This update changes the modpack loader from {current_loader.title()} "
                    f"to {loader_name.title()}, which is not supported automatically."
                )
            if InstanceRunLock.is_active(instance):
                blockers.append("Close Minecraft before updating this modpack.")

            root = Path(instance.instance_dir)
            old_files = {
                str(item.get("path") or "").casefold(): item
                for item in registry.get("managedFiles", [])
                if isinstance(item, dict) and str(item.get("path") or "").strip()
            }
            verification_cache = ModrinthPackRegistry._normalize_verification_cache(
                registry.get("verificationCache", {}),
                registry.get("managedFiles", []),
            )
            changes: dict[str, ModrinthPackUpdateChange] = {}
            preserved: dict[str, str] = {}
            old_unmodified: set[str] = set()

            for key, entry in old_files.items():
                path = ModrinthPackUpdateManager._target(root, str(entry.get("path") or ""))
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                if verified:
                    old_unmodified.add(key)
                elif path.exists():
                    preserved[key] = "modified-by-user"

            for key, entry in managed_files.items():
                target = ModrinthPackUpdateManager._target(root, str(entry["path"]))
                if key not in old_files and target.exists():
                    verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                    if not verified:
                        preserved[key] = "unmanaged-existing-file"

            for key, reason in preserved.items():
                entry = managed_files.get(key) or old_files.get(key) or {}
                changes[key] = ModrinthPackUpdateChange(
                    path=str(entry.get("path") or key),
                    action="preserve",
                    reason=reason,
                )

            for key, entry in old_files.items():
                if key in managed_files or key not in old_unmodified:
                    continue
                target = ModrinthPackUpdateManager._target(root, str(entry.get("path") or ""))
                if target.is_file():
                    changes[key] = ModrinthPackUpdateChange(
                        path=str(entry.get("path") or key),
                        action="remove",
                        reason="removed-by-pack-update",
                    )

            selected_by_path = {
                str(item.get("path") or "").replace("\\", "/").casefold(): item
                for item in selected_files
            }
            for key, entry in managed_files.items():
                if key in preserved:
                    continue
                target = ModrinthPackUpdateManager._target(root, str(entry["path"]))
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                if verified:
                    action = "unchanged"
                    reason = "already-matches-target"
                else:
                    action = "replace" if target.exists() else "add"
                    reason = "target-version-file"
                item = selected_by_path.get(key, {})
                download_bytes = int(item.get("fileSize", 0) or 0) if action in {"add", "replace"} else 0
                changes[key] = ModrinthPackUpdateChange(
                    path=str(entry.get("path") or key),
                    action=action,
                    reason=reason,
                    download_bytes=max(0, download_bytes),
                )

            return ModrinthPackUpdatePlan(
                instance_name=instance.name,
                pack_name=project.title,
                current_version=str(registry.get("versionNumber") or current_version_id),
                target_version=target_version.version_number,
                target_version_id=target_version.version_id,
                minecraft_version=minecraft_version,
                loader=loader_name,
                loader_version=loader_version,
                changes=tuple(sorted(changes.values(), key=lambda change: change.path.casefold())),
                blockers=tuple(blockers),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def update(instance: Instance, target_version_id: str = "", allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthPackUpdateResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before updating this modpack.")
        registry = ModrinthPackRegistry.load(instance)
        project_id = str(registry.get("projectId") or "").strip()
        current_version_id = str(registry.get("versionId") or "").strip()
        if not project_id or not current_version_id:
            raise RuntimeError("This instance is not managed by a Modrinth modpack.")

        target_id = str(target_version_id or "").strip()
        if not target_id:
            update_info = ModrinthPackUpdateManager.check(instance, allowed_version_types, force_refresh=True)
            if update_info is None or not update_info.available:
                raise RuntimeError("This Modrinth modpack is already up to date.")
            target_id = update_info.target_version_id

        project = ModrinthClient.get_project(project_id)
        target_version = ModrinthClient.get_version(target_id, force_refresh=True)
        if target_version.project_id != project_id:
            raise RuntimeError("The selected update does not belong to this Modrinth modpack.")
        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        if target_version.version_type not in allowed_types:
            raise RuntimeError(f"The selected modpack update uses the disabled {target_version.version_type} channel.")

        pack_file = target_version.primary_file(".mrpack")
        pack_path = Paths.modrinth_pack_cache(project_id, target_version.version_id, pack_file.filename)
        if reporter is None:
            ModrinthDownloader.download_file(pack_file, pack_path)
        else:
            ModrinthDownloader.download_file(pack_file, pack_path, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODPACK, progress_message=f"Downloading {project.title} update manifest...")
        staging = Paths.modrinth_staging_root() / f"update-{uuid4().hex}"
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
                raise RuntimeError(f"This update changes the modpack loader from {current_loader.title()} to {loader_name.title()}, which is not supported automatically.")
            base_version = VersionManager.load(minecraft_version)
            resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
            ModLoaderManager.prepare(base_version, *resolved_loader, reporter=reporter)

            old_files = {str(item.get("path") or "").casefold(): item for item in registry.get("managedFiles", []) if isinstance(item, dict) and str(item.get("path") or "").strip()}
            verification_cache = ModrinthPackRegistry._normalize_verification_cache(registry.get("verificationCache", {}), registry.get("managedFiles", []))
            preserved: dict[str, dict] = {}
            old_unmodified: set[str] = set()
            for key, entry in old_files.items():
                path = ModrinthPackUpdateManager._target(root, str(entry.get("path") or ""))
                expected = str(entry.get("sha1") or "").lower()
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                if verified:
                    old_unmodified.add(key)
                elif path.exists():
                    preserved[key] = {"path": str(entry.get("path") or ""), "reason": "modified-by-user", "previousSha1": expected, "targetSha1": str(managed_files.get(key, {}).get("sha1") or "")}

            for key, entry in managed_files.items():
                target = ModrinthPackUpdateManager._target(root, str(entry["path"]))
                if key not in old_files and target.exists():
                    verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                    current_hash = ModrinthPackUpdateManager._sha1(target) if target.is_file() and not verified else str(entry.get("sha1") or "").lower()
                    if not verified:
                        preserved[key] = {"path": entry["path"], "reason": "unmanaged-existing-file", "previousSha1": current_hash, "targetSha1": str(entry.get("sha1") or "")}

            selected_by_path = {str(item.get("path") or "").replace("\\", "/").casefold(): item for item in selected_files}
            pending_downloads: list[dict] = []
            for key, item in selected_by_path.items():
                entry = managed_files.get(key)
                if entry is None or key in preserved:
                    continue
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                if not verified:
                    pending_downloads.append(item)
            if reporter is None:
                ModrinthPackInstaller._download_files(pending_downloads, staging)
            else:
                ModrinthPackInstaller._download_files(pending_downloads, staging, reporter)

            backup_path = InstanceBackupManager.create(instance, InstanceBackupManager.SCOPE_FULL, reason="pre-modpack-update").backup.path
            removed = 0
            replaced = 0
            added = 0
            unchanged = 0
            applied_managed: list[dict] = []

            for key, entry in old_files.items():
                if key in managed_files or key not in old_unmodified:
                    continue
                target = ModrinthPackUpdateManager._target(root, str(entry.get("path") or ""))
                if target.is_file():
                    target.unlink()
                    removed += 1
                    ModrinthPackUpdateManager._remove_empty_parents(target.parent, root)

            for key, entry in managed_files.items():
                if key in preserved:
                    applied_managed.append(entry)
                    continue
                relative = ModrinthPackUpdateManager._relative(str(entry["path"]))
                source = staging.joinpath(*relative.parts)
                target = root.joinpath(*relative.parts)
                verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=verification_cache)
                if verified:
                    unchanged += 1
                    applied_managed.append(entry)
                    continue
                existed = target.exists()
                if not source.is_file():
                    raise RuntimeError(f"The staged modpack file is missing: {relative.as_posix()}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                replaced += int(existed)
                added += int(not existed)
                applied_managed.append(entry)

            updated = InstanceManager.set_runtime_profile(instance.name, base_version, resolved_loader)
            verification_cache = ModrinthPackRegistry.build_verification_cache(updated.instance_dir, applied_managed)
            ModrinthPackRegistry.save(updated.instance_dir, {
                "projectId": project_id,
                "versionId": target_version.version_id,
                "name": project.title,
                "versionNumber": target_version.version_number,
                "versionType": target_version.version_type,
                "datePublished": target_version.date_published,
                "minecraftVersion": minecraft_version,
                "loader": loader_name,
                "loaderVersion": loader_version,
                "installOptionalFiles": bool(registry.get("installOptionalFiles", True)),
                "managedFiles": applied_managed,
                "preservedFiles": list(preserved.values()),
                "verificationCache": verification_cache,
                "lastBackup": str(backup_path),
            })
            return ModrinthPackUpdateResult(instance_name=instance.name, pack_name=project.title, previous_version=str(registry.get("versionNumber") or current_version_id), target_version=target_version.version_number, added_files=added, replaced_files=replaced, removed_files=removed, preserved_files=tuple(sorted(item["path"] for item in preserved.values())), backup_path=backup_path, unchanged_files=unchanged)
        except Exception as error:
            if backup_path is not None:
                try:
                    InstanceBackupManager.restore(instance, backup_path, create_safety_backup=False)
                    old_version = VersionManager.load(previous_profile[0])
                    InstanceManager.set_runtime_profile(instance.name, old_version, previous_profile[1])
                    ModrinthPackRegistry.save(instance.instance_dir, registry)
                except Exception as rollback_error:
                    raise RuntimeError(f"Modpack update failed and rollback also failed: {rollback_error}") from error
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _registry_loader(registry: dict) -> str:
        loader_name = str(registry.get("loader") or ModLoaderManager.FABRIC).strip().lower()
        if loader_name not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError(f"Unsupported Modrinth modpack loader: {loader_name or 'unknown'}")
        return loader_name

    @staticmethod
    def _relative(value: str):
        relative = ModrinthPackRegistry._safe_relative(value)
        if relative is None:
            raise RuntimeError(f"Unsafe managed Modrinth path: {value!r}")
        return relative

    @staticmethod
    def _target(root: Path, value: str) -> Path:
        relative = ModrinthPackUpdateManager._relative(value)
        return root.joinpath(*relative.parts)

    @staticmethod
    def _sha1(path: Path) -> str:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _remove_empty_parents(directory: Path, root: Path) -> None:
        current = directory
        root_resolved = root.resolve()
        while current.exists() and current.resolve() != root_resolved:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
