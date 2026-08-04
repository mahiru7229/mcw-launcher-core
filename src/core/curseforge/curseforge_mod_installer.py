from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import shutil

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.curseforge.file import CurseForgeFile
from src.models.curseforge.install_result import CurseForgeModInstallResult
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.curseforge.project import CurseForgeProject
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo
from src.models.progress.progress_stage import ProgressStage


@dataclass(slots=True)
class _PreparedMod:
    file: CurseForgeFile
    project: CurseForgeProject
    cache_path: Path
    metadata: ModInfo
    previous_entry: dict
    entry: dict
    allow_unverified: bool


@dataclass(frozen=True, slots=True)
class _TransactionSnapshot:
    directory: Path
    affected_paths: tuple[Path, ...]
    backups: tuple[tuple[Path, Path], ...]


class CurseForgeModInstaller:
    MAX_DEPENDENCIES = 64

    @staticmethod
    def install(instance: Instance, project_id: int, file_id: int, install_dependencies: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, allow_unverified: bool = False) -> CurseForgeModInstallResult:
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError("CurseForge mod installation requires a Fabric, Quilt, Forge, or NeoForge instance.")
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before installing or updating mods.")

        allowed = CurseForgeClient.normalize_release_types(allowed_release_types)
        if reporter is not None:
            reporter.status(ProgressStage.CHECKING_MODS, f"Resolving CurseForge dependencies for {loader_name.title()}...")
        root = CurseForgeClient.get_file(project_id, file_id)
        if root.release_type not in allowed:
            raise RuntimeError(f"CurseForge file '{root.display_name}' uses the disabled {root.release_type} channel.")
        plan = CurseForgeModInstaller._build_plan(root, instance.version_id, loader_name, install_dependencies, allowed)
        projects = CurseForgeClient.get_projects_batch({item.project_id for item in plan})
        registry = CurseForgeRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        prepared: list[_PreparedMod] = []
        warnings: list[str] = []
        manual_downloads: list[CurseForgeManualDownload] = []

        for index, file in enumerate(plan, start=1):
            project = projects.get(file.project_id) or CurseForgeClient.get_project(file.project_id)
            existing = mods.get(str(file.project_id), {})
            previous_entry = dict(existing) if isinstance(existing, dict) else {}
            entry = CurseForgeModInstaller._registry_entry(file, project, instance, loader_name)
            if reporter is not None:
                reporter.files(
                    stage=ProgressStage.DOWNLOADING_MODS,
                    message=f"Preparing {project.name} ({index}/{len(plan)})...",
                    current=index - 1,
                    total=len(plan),
                )
            try:
                cache = Paths.curseforge_file_cache(file.project_id, file.file_id, file.file_name)
                CurseForgeDownloader.download_file(
                    file,
                    cache,
                    reporter=reporter,
                    stage=ProgressStage.DOWNLOADING_MODS,
                    message=f"Downloading {project.name}...",
                    project_name=project.name,
                )
                metadata = ModManager.read_mod(cache, preferred_loader=loader_name)
                root_override = bool(
                    allow_unverified
                    and file.project_id == root.project_id
                    and file.file_id == root.file_id
                )
                ModManager.validate_mod_for_instance(instance, metadata, allow_unverified=root_override)
                compatibility_warning = ModManager.compatibility_warning(instance, metadata)
                CurseForgeModInstaller._ensure_unique_mod_id(prepared, metadata, project.name)
                entry.update({
                    "modId": metadata.mod_id,
                    "validatedLoader": metadata.loader,
                    "metadataFormat": metadata.metadata_format,
                    "pendingDownload": False,
                    "lastDownloadError": "",
                    "retryableDownload": True,
                    "acceptedUnverified": bool(compatibility_warning),
                    "compatibilityWarning": compatibility_warning,
                })
                prepared.append(
                    _PreparedMod(
                        file=file,
                        project=project,
                        cache_path=cache,
                        metadata=metadata,
                        previous_entry=previous_entry,
                        entry=entry,
                        allow_unverified=root_override,
                    )
                )
                if compatibility_warning:
                    warnings.append(f"{project.name}: installed with compatibility warning: {compatibility_warning}")
            except CurseForgeManualDownloadRequired as error:
                requirement = CurseForgeModInstaller._manual_requirement(error, project)
                entry.update({
                    "pendingDownload": True,
                    "lastDownloadError": requirement.reason,
                    "retryableDownload": False,
                    "acceptedUnverified": False,
                    "compatibilityWarning": "",
                })
                manual_downloads.append(requirement)
                warnings.append(f"{project.name}: manual download required")
            mods[str(file.project_id)] = entry
            if reporter is not None:
                reporter.files(
                    stage=ProgressStage.DOWNLOADING_MODS,
                    message=f"Prepared {project.name} ({index}/{len(plan)})",
                    current=index,
                    total=len(plan),
                )

        installed_projects, installed_files = CurseForgeModInstaller._apply_transaction(
            instance,
            prepared,
            registry,
            mods,
            reporter,
        )
        return CurseForgeModInstallResult(
            installed_projects=tuple(installed_projects),
            installed_files=tuple(installed_files),
            warnings=tuple(warnings),
            manual_downloads=tuple(manual_downloads),
            instance_name=instance.name,
        )

    @staticmethod
    def _apply_transaction(instance: Instance, prepared: list[_PreparedMod], registry: dict, mods: dict, reporter: ProgressReporter | None) -> tuple[list[str], list[str]]:
        if not prepared:
            CurseForgeRegistry.save(instance, registry)
            return [], []

        snapshot = CurseForgeModInstaller._create_snapshot(instance, prepared)
        installed_projects: list[str] = []
        installed_files: list[str] = []
        try:
            for index, item in enumerate(prepared, start=1):
                if reporter is not None:
                    reporter.files(
                        stage=ProgressStage.CHECKING_MODS,
                        message=f"Installing {item.project.name} ({index}/{len(prepared)})...",
                        current=index - 1,
                        total=len(prepared),
                    )
                added = ModManager.add_mods(
                    instance,
                    [item.cache_path],
                    replace=True,
                    allow_unverified=item.allow_unverified,
                )
                if not added:
                    raise RuntimeError(f"'{item.project.name}' was downloaded but could not be added to the instance.")
                installed = added[0]
                old_name = str(item.previous_entry.get("fileName") or "")
                if old_name and old_name.casefold() != installed.file_name.casefold():
                    CurseForgeModInstaller._remove_tracked_file(instance, old_name)
                item.entry["fileName"] = installed.file_name
                mods[str(item.file.project_id)] = item.entry
                installed_projects.append(item.project.name)
                installed_files.append(installed.file_name)
                if reporter is not None:
                    reporter.files(
                        stage=ProgressStage.CHECKING_MODS,
                        message=f"Installed {item.project.name} ({index}/{len(prepared)})",
                        current=index,
                        total=len(prepared),
                    )
            CurseForgeRegistry.save(instance, registry)
        except Exception as error:
            try:
                CurseForgeModInstaller._restore_snapshot(snapshot)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"CurseForge installation failed and its rollback could not be completed: {rollback_error}"
                ) from error
            raise
        finally:
            shutil.rmtree(snapshot.directory, ignore_errors=True)
        return installed_projects, installed_files

    @staticmethod
    def _create_snapshot(instance: Instance, prepared: list[_PreparedMod]) -> _TransactionSnapshot:
        transaction = Paths.curseforge_instance_transaction_root(instance) / uuid4().hex
        backups_dir = transaction / "backups"
        backups_dir.mkdir(parents=True, exist_ok=False)
        mods_dir = Paths.instance_mods_dir(instance)
        installed = ModManager.list_mods(instance)
        registry_path = Paths.curseforge_instance_registry(instance)
        affected: set[Path] = {
            registry_path,
            registry_path.with_suffix(registry_path.suffix + ".part"),
        }

        for item in prepared:
            destination = mods_dir / item.cache_path.name
            affected.update({
                destination,
                destination.with_name(destination.name + ModManager.DISABLED_SUFFIX),
                destination.with_name(destination.name + ".part"),
            })
            if item.metadata.mod_id != "unknown":
                affected.update(
                    mod.path
                    for mod in installed
                    if mod.mod_id != "unknown" and mod.mod_id.casefold() == item.metadata.mod_id.casefold()
                )
            old_name = str(item.previous_entry.get("fileName") or "")
            old_path = CurseForgeRegistry.safe_tracked_path(instance, old_name) if old_name else None
            if old_path is not None:
                affected.add(old_path)
                affected.add(old_path.with_name(old_path.name + ModManager.DISABLED_SUFFIX))

        backups: list[tuple[Path, Path]] = []
        for index, path in enumerate(sorted(affected, key=lambda value: str(value).casefold())):
            if not path.is_file():
                continue
            backup = backups_dir / f"{index:04d}-{path.name}"
            shutil.copy2(path, backup)
            backups.append((path, backup))
        return _TransactionSnapshot(
            directory=transaction,
            affected_paths=tuple(affected),
            backups=tuple(backups),
        )

    @staticmethod
    def _restore_snapshot(snapshot: _TransactionSnapshot) -> None:
        for path in snapshot.affected_paths:
            if path.is_file():
                path.unlink()
        for path, backup in snapshot.backups:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".rollback")
            temporary.unlink(missing_ok=True)
            shutil.copy2(backup, temporary)
            temporary.replace(path)

    @staticmethod
    def _remove_tracked_file(instance: Instance, filename: str) -> None:
        old_path = CurseForgeRegistry.safe_tracked_path(instance, filename)
        if old_path is None:
            return
        old_path.unlink(missing_ok=True)
        old_path.with_name(old_path.name + ModManager.DISABLED_SUFFIX).unlink(missing_ok=True)

    @staticmethod
    def _ensure_unique_mod_id(prepared: list[_PreparedMod], metadata: ModInfo, project_name: str) -> None:
        if metadata.mod_id == "unknown":
            return
        conflict = next(
            (
                item
                for item in prepared
                if item.metadata.mod_id != "unknown"
                and item.metadata.mod_id.casefold() == metadata.mod_id.casefold()
            ),
            None,
        )
        if conflict is not None:
            raise RuntimeError(
                f"CurseForge projects '{conflict.project.name}' and '{project_name}' both provide mod ID "
                f"'{metadata.mod_id}'. Nothing was installed."
            )

    @staticmethod
    def _registry_entry(file: CurseForgeFile, project: CurseForgeProject, instance: Instance, loader_name: str) -> dict:
        return {
            "projectId": file.project_id,
            "fileId": file.file_id,
            "fileName": file.file_name,
            "displayName": project.name,
            "sha1": file.sha1,
            "size": file.file_length,
            "downloadUrl": file.download_url,
            "releaseType": file.release_type,
            "declaredLoaders": list(file.loaders),
            "gameVersions": list(file.game_versions),
            "gameVersion": instance.version_id,
            "loader": loader_name,
            "datePublished": file.file_date,
            "source": "curseforge",
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _manual_requirement(error: CurseForgeManualDownloadRequired, project: CurseForgeProject) -> CurseForgeManualDownload:
        return CurseForgeManualDownload(
            project_id=error.requirement.project_id,
            file_id=error.requirement.file_id,
            project_name=project.name,
            file_name=error.requirement.file_name,
            file_size=error.requirement.file_size,
            sha1=error.requirement.sha1,
            project_url=project.project_url or error.requirement.project_url,
            reason=error.requirement.reason,
        )

    @staticmethod
    def _build_plan(root: CurseForgeFile, game_version: str, loader: str, install_dependencies: bool, allowed_release_types: tuple[str, ...]) -> list[CurseForgeFile]:
        plan: list[CurseForgeFile] = []
        visited: set[int] = set()
        visiting: set[int] = set()
        normalized_loader = CurseForgeClient.normalize_loader(loader)

        def visit(file: CurseForgeFile) -> None:
            if file.project_id in visited:
                return
            if len(visited) >= CurseForgeModInstaller.MAX_DEPENDENCIES:
                raise RuntimeError("The CurseForge dependency graph is too large to install safely.")
            if file.release_type not in allowed_release_types:
                raise RuntimeError(f"Required CurseForge file '{file.display_name}' uses the disabled {file.release_type} channel.")
            # CurseForge game-version and loader labels are advisory. Some JARs
            # support nearby Minecraft patches or multiple loaders despite
            # incomplete provider metadata. ModManager validates the downloaded
            # JAR's real loader metadata before changing the instance.
            if file.project_id in visiting:
                return
            visiting.add(file.project_id)
            try:
                if install_dependencies:
                    for dependency in file.dependencies:
                        if not dependency.required:
                            continue
                        dependency_file = CurseForgeClient.latest_compatible_file(
                            dependency.project_id,
                            game_version,
                            loader=normalized_loader,
                            release_types=allowed_release_types,
                        )
                        visit(dependency_file)
            finally:
                visiting.discard(file.project_id)
            visited.add(file.project_id)
            plan.append(file)

        visit(root)
        return plan
