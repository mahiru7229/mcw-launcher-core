from __future__ import annotations

from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.update import ModrinthModUpdateEntry, ModrinthModUpdateReport, ModrinthModUpdateResult
from src.models.progress.progress_stage import ProgressStage


class ModrinthModUpdateManager:
    @staticmethod
    def check(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, force_refresh: bool = False, reporter: ProgressReporter | None = None) -> ModrinthModUpdateReport:
        loader_name = ModrinthModUpdateManager._supported_loader(instance)
        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        registry = ModrinthRegistry.load(instance)
        tracked = [(project_id, raw_entry) for project_id, raw_entry in registry.get("mods", {}).items() if isinstance(raw_entry, dict)]
        entries: list[ModrinthModUpdateEntry] = []
        total = max(len(tracked), 1)

        if not tracked and reporter is not None:
            reporter.steps(ProgressStage.CHECKING_MODS, "mods.update_check.no_tracked_mods", 1, 1)

        for index, (project_id, raw_entry) in enumerate(tracked, start=1):
            if reporter is not None:
                reporter.steps(ProgressStage.CHECKING_MODS, "mods.update_check.checking_project", index - 1, total)
            entry = ModrinthModUpdateManager._check_entry(instance, str(project_id), raw_entry, loader_name, allowed_types, force_refresh)
            entries.append(entry)
            if reporter is not None:
                reporter.steps(ProgressStage.CHECKING_MODS, "mods.update_check.checked_project", index, total)

        entries.sort(key=lambda item: (not item.update_available, item.locked, item.title.casefold()))
        return ModrinthModUpdateReport(entries=tuple(entries))

    @staticmethod
    def update(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult:
        loader_name = ModrinthModUpdateManager._supported_loader(instance)
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before updating mods.")

        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        registry = ModrinthRegistry.load(instance)
        mods = registry.get("mods", {})
        selected_ids = [str(project_id).strip() for project_id in project_ids if str(project_id).strip()]
        updated_projects: list[str] = []
        updated_files: list[str] = []
        skipped_locked: list[str] = []
        warnings: list[str] = []

        for project_id in dict.fromkeys(selected_ids):
            raw_entry = mods.get(project_id)
            if not isinstance(raw_entry, dict):
                warnings.append(f"Modrinth project '{project_id}' is no longer tracked in this instance.")
                continue
            title = str(raw_entry.get("title") or project_id)
            if bool(raw_entry.get("locked", False)):
                skipped_locked.append(title)
                continue
            try:
                latest = ModrinthClient.select_version(project_id, game_version=instance.version_id, loader=loader_name, version_types=allowed_types)
                current = ModrinthModUpdateManager._current_version(raw_entry, allowed_types=allowed_types)
            except RuntimeError as error:
                warnings.append(f"{title}: {error}")
                continue
            if latest.version_id == str(raw_entry.get("versionId") or "") or not ModrinthModUpdateManager._is_newer(latest, current):
                continue
            result = ModrinthModInstaller.install(instance, latest.version_id, install_dependencies=True, allowed_version_types=allowed_types, reporter=reporter)
            updated_projects.extend(result.installed_projects)
            updated_files.extend(result.installed_files)
            warnings.extend(result.warnings)
            registry = ModrinthRegistry.load(instance)
            mods = registry.get("mods", {})

        return ModrinthModUpdateResult(updated_projects=tuple(dict.fromkeys(updated_projects)), updated_files=tuple(dict.fromkeys(updated_files)), skipped_locked=tuple(dict.fromkeys(skipped_locked)), warnings=tuple(warnings))

    @staticmethod
    def update_all(instance: Instance, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None) -> ModrinthModUpdateResult:
        registry = ModrinthRegistry.load(instance)
        return ModrinthModUpdateManager.update(instance, list(registry.get("mods", {})), allowed_version_types, reporter)

    @staticmethod
    def set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]:
        ModrinthModUpdateManager._supported_loader(instance)
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before changing mod version locks.")
        return ModrinthRegistry.set_locked(instance, project_ids, locked)

    @staticmethod
    def _check_entry(instance: Instance, project_id: str, raw_entry: dict, loader_name: str, allowed_types: tuple[str, ...], force_refresh: bool) -> ModrinthModUpdateEntry:
        title = str(raw_entry.get("title") or project_id)
        file_name = str(raw_entry.get("fileName") or "")
        current_version_id = str(raw_entry.get("versionId") or "")
        current_version_number = str(raw_entry.get("versionNumber") or "Unknown")
        tracked_path = ModrinthRegistry.safe_tracked_path(instance, file_name)
        file_missing = tracked_path is None or (not tracked_path.exists() and not tracked_path.with_name(tracked_path.name + ".disabled").exists())

        try:
            versions = ModrinthClient.list_project_versions(project_id, loader=loader_name, game_version=instance.version_id, version_types=allowed_types, force_refresh=force_refresh)
            latest = versions[0] if versions else None
            if latest is None:
                raise RuntimeError(f"No allowed {loader_name.title()} version is available.")
            current = ModrinthModUpdateManager._current_version(raw_entry, versions=versions, allowed_types=allowed_types)
            if not ModrinthModUpdateManager._is_newer(latest, current):
                latest = current or latest
            latest_version_id = latest.version_id
            latest_version_number = latest.version_number
            latest_version_type = latest.version_type
            warning = ""
        except RuntimeError as error:
            latest_version_id = current_version_id
            latest_version_number = current_version_number
            latest_version_type = str(raw_entry.get("versionType") or "release")
            warning = str(error)

        return ModrinthModUpdateEntry(project_id=project_id, title=title, file_name=file_name, current_version_id=current_version_id, current_version_number=current_version_number, latest_version_id=latest_version_id, latest_version_number=latest_version_number, latest_version_type=latest_version_type, locked=bool(raw_entry.get("locked", False)), file_missing=file_missing, warning=warning)

    @staticmethod
    def _current_version(raw_entry: dict, versions=(), allowed_types: tuple[str, ...] = ("release", "beta", "alpha")):
        version_id = str(raw_entry.get("versionId") or "")
        if not version_id:
            return None
        for version in versions:
            if version.version_id == version_id:
                return version
        current_type = str(raw_entry.get("versionType") or "release").lower()
        if current_type in allowed_types:
            return None
        try:
            return ModrinthClient.get_version(version_id)
        except RuntimeError:
            return None

    @staticmethod
    def _is_newer(candidate, current) -> bool:
        if current is None:
            return True
        if candidate.version_id == current.version_id:
            return False
        candidate_time = ModrinthClient._published_timestamp(candidate.date_published)
        current_time = ModrinthClient._published_timestamp(current.date_published)
        if candidate_time and current_time:
            return candidate_time > current_time
        return True

    @staticmethod
    def _supported_loader(instance: Instance) -> str:
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError("Mod updates require a Fabric, Quilt, Forge, or NeoForge instance.")
        return loader_name
