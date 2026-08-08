from __future__ import annotations

from datetime import datetime, timezone

from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.network.artifact_download_service import ArtifactDownloadError, is_local_artifact_storage_error
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.install_result import ModrinthModInstallResult
from src.models.modrinth.manual_download import ModrinthManualDownload
from src.models.modrinth.project import ModrinthProject
from src.models.modrinth.version import ModrinthVersion
from src.models.progress.progress_stage import ProgressStage


class ModrinthModInstaller:
    MAX_DEPENDENCIES = 64
    SUPPORTED_LOADERS = ModLoaderManager.MODDED_LOADERS

    @staticmethod
    def install(instance: Instance, version_id: str, install_dependencies: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModInstallResult:
        loader_name = ModrinthModInstaller._supported_loader(instance)
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before installing or updating mods.")

        root_version = ModrinthClient.get_version(version_id)
        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        if root_version.version_type not in allowed_types:
            raise RuntimeError(f"Modrinth version '{root_version.version_number}' uses the disabled {root_version.version_type} channel.")
        registry = ModrinthRegistry.load(instance)
        registry_mods = registry.setdefault("mods", {})
        locked_dependencies = {project_id for project_id, entry in registry_mods.items() if project_id != root_version.project_id and isinstance(entry, dict) and bool(entry.get("locked", False))}
        plan, projects, warnings = ModrinthModInstaller._build_plan(root_version, instance.version_id, loader_name, install_dependencies, allowed_types, locked_dependencies)
        installed_projects: list[str] = []
        installed_files: list[str] = []
        manual_downloads: list[ModrinthManualDownload] = []

        for version in plan:
            project = projects[version.project_id]
            file = version.primary_file(".jar")
            cache_path = Paths.modrinth_file_cache(version.project_id, version.version_id, file.filename)
            previous = registry_mods.get(version.project_id, {}) if isinstance(registry_mods.get(version.project_id), dict) else {}
            entry = {
                "projectId": version.project_id,
                "versionId": version.version_id,
                "versionNumber": version.version_number,
                "versionType": version.version_type,
                "fileName": file.filename,
                "sha1": file.sha1,
                "sha512": file.sha512,
                "size": file.size,
                "downloadUrls": [file.url],
                "title": project.title,
                "loader": loader_name,
                "locked": bool(previous.get("locked", False)),
                "source": "modrinth",
                "datePublished": version.date_published,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            try:
                project_url = f"https://modrinth.com/mod/{project.slug or project.project_id}"
                version_url = f"{project_url}/version/{version.version_id}"
                if reporter is None:
                    ModrinthDownloader.download_file(file, cache_path, purpose="mod", page_url=version_url, project_url=project_url, project_id=version.project_id, version_id=version.version_id)
                else:
                    ModrinthDownloader.download_file(file, cache_path, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODS, progress_message=f"Downloading {project.title}...", purpose="mod", page_url=version_url, project_url=project_url, project_id=version.project_id, version_id=version.version_id)
            except ArtifactDownloadError as error:
                if is_local_artifact_storage_error(error):
                    raise
                entry["pendingDownload"] = True
                entry["lastDownloadError"] = str(error)
                entry["downloadFailure"] = error.failure.to_dict()
                registry_mods[version.project_id] = entry
                manual_downloads.append(ModrinthManualDownload(
                    project_id=version.project_id,
                    version_id=version.version_id,
                    project_name=project.title,
                    file_name=file.filename,
                    file_size=file.size,
                    sha1=file.sha1,
                    sha512=file.sha512,
                    project_url=error.failure.project_url or project_url,
                    version_url=error.failure.page_url or version_url,
                    direct_url=error.failure.url or file.url,
                    reason=f"Automatic download failed ({error.failure.reason.value}): {error.failure.detail}",
                    failure_reason=error.failure.reason.value,
                    http_status=error.failure.http_status,
                    attempts=error.failure.attempts,
                    retryable=error.failure.retryable,
                ))
                warnings.append(f"{project.title}: automatic download failed ({error.failure.reason.value}); manual download is available.")
                continue

            metadata = ModManager.read_mod(cache_path, preferred_loader=loader_name, provider_version=version.version_number)
            ModManager.validate_mod_for_instance(instance, metadata)
            added = ModManager.add_mods(instance, [cache_path], replace=True)
            if not added:
                raise RuntimeError(f"Mod '{project.title}' was downloaded but could not be added to the instance.")

            previous_name = str(previous.get("fileName") or "")
            new_name = added[0].file_name
            if previous_name and previous_name.casefold() != new_name.casefold():
                previous_path = ModrinthRegistry.safe_tracked_path(instance, previous_name)
                if previous_path is not None:
                    previous_path.unlink(missing_ok=True)
                    previous_path.with_name(previous_path.name + ModManager.DISABLED_SUFFIX).unlink(missing_ok=True)

            entry["fileName"] = new_name
            entry["pendingDownload"] = False
            entry["lastDownloadError"] = ""
            registry_mods[version.project_id] = entry
            installed_projects.append(project.title)
            installed_files.append(new_name)

        ModrinthRegistry.save(instance, registry)
        return ModrinthModInstallResult(installed_projects=tuple(installed_projects), installed_files=tuple(installed_files), warnings=tuple(warnings), manual_downloads=tuple(manual_downloads), instance_name=instance.name)

    @staticmethod
    def _build_plan(root_version: ModrinthVersion, game_version: str, loader_name: str, install_dependencies: bool, allowed_version_types: tuple[str, ...] = ("release", "beta", "alpha"), locked_dependency_projects: set[str] | None = None) -> tuple[list[ModrinthVersion], dict[str, ModrinthProject], list[str]]:
        normalized_loader = ModrinthModInstaller._normalize_loader(loader_name)
        plan: list[ModrinthVersion] = []
        projects: dict[str, ModrinthProject] = {}
        warnings: list[str] = []
        visited_versions: set[str] = set()
        visiting_projects: set[str] = set()
        selected_projects: dict[str, str] = {}
        locked_dependency_projects = set(locked_dependency_projects or ())

        def visit(version: ModrinthVersion) -> None:
            if version.version_id in visited_versions:
                return
            if len(visited_versions) >= ModrinthModInstaller.MAX_DEPENDENCIES:
                raise RuntimeError("The Modrinth dependency graph is too large to install safely.")
            if version.version_type not in allowed_version_types:
                raise RuntimeError(f"Required Modrinth version '{version.version_number}' uses the disabled {version.version_type} channel.")
            ModrinthModInstaller._validate_version(version, game_version, normalized_loader)
            selected_version = selected_projects.get(version.project_id)
            if selected_version is not None and selected_version != version.version_id:
                warnings.append(f"Conflicting dependency versions for project {version.project_id}; keeping {selected_version} and skipping {version.version_id}.")
                return
            selected_projects[version.project_id] = version.version_id

            project = projects.get(version.project_id)
            if project is None:
                project = ModrinthClient.get_project(version.project_id)
                projects[version.project_id] = project
            if project.project_type != "mod":
                raise RuntimeError(f"'{project.title}' is not a Modrinth mod project.")
            if project.client_side == "unsupported":
                raise RuntimeError(f"'{project.title}' does not support the Minecraft client.")

            if version.project_id in visiting_projects:
                return
            visiting_projects.add(version.project_id)
            try:
                if install_dependencies:
                    for dependency in version.dependencies:
                        if dependency.dependency_type != "required":
                            continue
                        if dependency.project_id and dependency.project_id in locked_dependency_projects:
                            warnings.append(f"Locked dependency project {dependency.project_id} was kept at its installed version.")
                            continue
                        dependency_version = ModrinthModInstaller._resolve_dependency(dependency.version_id, dependency.project_id, game_version, normalized_loader, allowed_version_types)
                        if dependency_version is None:
                            label = dependency.file_name or dependency.project_id or dependency.version_id or "unknown dependency"
                            warnings.append(f"Required external dependency could not be installed automatically: {label}")
                            continue
                        visit(dependency_version)
            finally:
                visiting_projects.discard(version.project_id)

            visited_versions.add(version.version_id)
            plan.append(version)

        visit(root_version)
        return plan, projects, warnings

    @staticmethod
    def _resolve_dependency(version_id: str, project_id: str, game_version: str, loader_name: str, allowed_version_types: tuple[str, ...] = ("release", "beta", "alpha")) -> ModrinthVersion | None:
        if version_id:
            return ModrinthClient.get_version(version_id)
        if project_id:
            return ModrinthClient.select_version(project_id, game_version=game_version, loader=loader_name, version_types=allowed_version_types)
        return None

    @staticmethod
    def _validate_version(version: ModrinthVersion, game_version: str, loader_name: str) -> None:
        normalized_loaders = {str(loader).strip().lower() for loader in version.loaders}
        compatible_loaders = set(ModrinthClient.compatible_loaders(loader_name))
        if not compatible_loaders.intersection(normalized_loaders):
            raise RuntimeError(f"Modrinth version '{version.version_number}' does not support {loader_name.title()}.")
        # Modrinth game-version labels are advisory. Nearby patch releases can
        # share a compatible JAR, so installation is gated by loader and actual
        # JAR validation rather than this provider-maintained list.
        version.primary_file(".jar")

    @staticmethod
    def _supported_loader(instance: Instance) -> str:
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        return ModrinthModInstaller._normalize_loader(loader_name)

    @staticmethod
    def _normalize_loader(loader_name: str) -> str:
        normalized = str(loader_name or "").strip().lower()
        if normalized not in ModrinthModInstaller.SUPPORTED_LOADERS:
            raise RuntimeError("Modrinth mod installation requires a Fabric, Quilt, Forge, or NeoForge instance.")
        return normalized
