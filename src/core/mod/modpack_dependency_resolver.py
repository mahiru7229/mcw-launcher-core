from __future__ import annotations

from collections import deque
import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from time import sleep
from typing import Callable, TypeVar

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.mod.mod_compatibility_manager import ModCompatibilityManager
from src.core.mod.mod_manager import ModManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.network.download_pause import download_pause_controller
from src.core.network.retry_policy import DownloadRetryPolicy
from src.core.progress.progress_reporter import ProgressReporter
from src.models.curseforge.file import CurseForgeDependency, CurseForgeFile
from src.models.instance.instance import Instance
from src.models.mod.dependency_resolution import DependencyResolutionResult, RequiredModDependenciesMissing
from src.models.mod.mod_issue import ModIssue
from src.models.modrinth.version import ModrinthVersion
from src.models.progress.progress_stage import ProgressStage


T = TypeVar("T")


class ModpackDependencyResolver:
    """Completes required provider dependency graphs for managed modpacks.

    A provider manifest remains authoritative for files it explicitly pins.
    This resolver only appends missing *required* dependencies and never
    replaces a pack-pinned version.
    """

    MAX_DEPTH = 20
    MAX_DEPENDENCIES = 256
    MAX_ATTEMPTS = 3
    MAX_COMPLETION_PASSES = 8
    BLOCKING_CODES = {"dependency-missing", "dependency-disabled", "dependency-version"}

    @staticmethod
    def resolve(instance: Instance, reporter: ProgressReporter | None = None) -> DependencyResolutionResult:
        if getattr(instance, "instance_dir", None) is None:
            return DependencyResolutionResult()
        added: list[str] = []
        warnings: list[str] = []
        unresolved: list[str] = []

        pruned = ModpackDependencyResolver._prune_redundant_embedded_dependencies(instance)
        warnings.extend(pruned)

        modrinth = ModrinthPackRegistry.load(instance)
        if ModpackDependencyResolver._has_managed_mods(modrinth.get("managedFiles", [])):
            result = ModpackDependencyResolver._resolve_modrinth(instance, modrinth, reporter)
            added.extend(result.added_files)
            warnings.extend(result.warnings)
            unresolved.extend(result.unresolved)

        curseforge = CurseForgePackRegistry.load(Path(instance.instance_dir))
        if ModpackDependencyResolver._has_managed_mods(curseforge.get("managedFiles", [])):
            result = ModpackDependencyResolver._resolve_curseforge(instance, curseforge, reporter)
            added.extend(result.added_files)
            warnings.extend(result.warnings)
            unresolved.extend(result.unresolved)

        # Legacy packs can pin a dependency in their manifest while storing it
        # in a version-specific mods directory or leaving a stale/missing local
        # file behind. Reconcile the dependency audit with the authoritative
        # pack registry before attempting a cross-provider replacement.
        result = ModpackDependencyResolver._reconcile_pack_pinned_dependencies(instance, reporter)
        added.extend(result.added_files)
        warnings.extend(result.warnings)
        unresolved.extend(result.unresolved)

        # CurseForge file relations are not always complete. Once the pack JARs
        # exist locally, use the exact file hash to find the same release on
        # Modrinth and recover required relations from that provider. This is
        # identity-based enrichment, not a name-only search or a hardcoded mod.
        result = ModpackDependencyResolver._resolve_cross_provider_missing(instance, reporter)
        added.extend(result.added_files)
        warnings.extend(result.warnings)
        unresolved.extend(result.unresolved)

        if added:
            ModProvenanceRegistry.synchronize(instance)
        return DependencyResolutionResult(
            added_files=tuple(dict.fromkeys(added)),
            warnings=tuple(dict.fromkeys(warnings)),
            unresolved=tuple(dict.fromkeys(unresolved)),
        )

    @staticmethod
    def blocking_issues(instance: Instance) -> tuple:
        report = ModCompatibilityManager.scan(instance)
        return tuple(
            issue
            for issue in report.issues
            if issue.severity == "error" and issue.code in ModpackDependencyResolver.BLOCKING_CODES
        )

    @staticmethod
    def raise_for_required_dependencies(instance: Instance, unresolved: tuple[str, ...] | list[str] = ()) -> None:
        if not ModpackDependencyResolver._is_managed_modpack(instance):
            return
        issues = list(ModpackDependencyResolver.blocking_issues(instance))
        issues.extend(
            ModIssue(severity="error", code="dependency-unresolved", message=str(message), mod_ids=())
            for message in unresolved
            if str(message).strip()
        )
        if issues:
            raise RequiredModDependenciesMissing(instance.name, tuple(issues))

    @staticmethod
    def _resolve_modrinth(instance: Instance, registry: dict, reporter: ProgressReporter | None) -> DependencyResolutionResult:
        entries = [entry for entry in registry.get("managedFiles", []) if isinstance(entry, dict)]
        mod_entries = [entry for entry in entries if ModpackDependencyResolver._is_mod_entry(entry)]
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        loader_name = str(loader_name).strip().casefold()
        selected: dict[str, dict] = {}
        versions: dict[str, ModrinthVersion] = {}
        warnings: list[str] = []
        unresolved: list[str] = []
        added: list[str] = []
        changed = False
        installed_identities = ModpackDependencyResolver._installed_mod_identities(instance)

        ModpackDependencyResolver._report(reporter, "Resolving Modrinth modpack dependencies...", 0, max(1, len(mod_entries)))
        for completed, entry in enumerate(mod_entries, start=1):
            download_pause_controller.raise_if_requested()
            entry.setdefault("selectionReason", "pack_manifest")
            entry.setdefault("requiredBy", [])
            try:
                version = ModpackDependencyResolver._modrinth_version_for_entry(entry)
            except Exception as error:
                warnings.append(f"Could not identify Modrinth dependency metadata for {entry.get('fileName') or entry.get('path')}: {error}")
                ModpackDependencyResolver._report(reporter, "Resolving Modrinth modpack dependencies...", completed, max(1, len(mod_entries)))
                continue
            if version is None:
                warnings.append(f"Modrinth file identity is unavailable: {entry.get('fileName') or entry.get('path')}")
                ModpackDependencyResolver._report(reporter, "Resolving Modrinth modpack dependencies...", completed, max(1, len(mod_entries)))
                continue
            changed |= ModpackDependencyResolver._hydrate_modrinth_entry(entry, version)
            selected.setdefault(version.project_id, entry)
            versions[version.version_id] = version
            ModpackDependencyResolver._report(reporter, "Resolving Modrinth modpack dependencies...", completed, max(1, len(mod_entries)))

        queue: deque[tuple[ModrinthVersion, int, str]] = deque(
            (version, 0, ModpackDependencyResolver._entry_label(selected.get(version.project_id, {}), version.project_id))
            for version in versions.values()
        )
        visited_versions: set[str] = set()
        discovered = 0

        while queue:
            version, depth, parent_label = queue.popleft()
            if version.version_id in visited_versions:
                continue
            if depth > ModpackDependencyResolver.MAX_DEPTH:
                unresolved.append(f"Modrinth dependency depth exceeded {ModpackDependencyResolver.MAX_DEPTH} at {parent_label}.")
                continue
            visited_versions.add(version.version_id)
            for dependency in version.dependencies:
                if dependency.dependency_type != "required":
                    continue
                download_pause_controller.raise_if_requested()
                if dependency.project_id and dependency.project_id in selected:
                    target = selected[dependency.project_id]
                    changed |= ModpackDependencyResolver._append_required_by(target, parent_label)
                    if dependency.version_id and str(target.get("versionId") or "") not in {"", dependency.version_id}:
                        warnings.append(
                            f"{parent_label} requests Modrinth version {dependency.version_id}, but the modpack pins "
                            f"{target.get('versionId')}; the pack-pinned file was kept."
                        )
                    continue
                try:
                    dependency_version = ModpackDependencyResolver._retry(
                        lambda dependency=dependency: ModrinthModInstaller._resolve_dependency(
                            dependency.version_id,
                            dependency.project_id,
                            instance.version_id,
                            loader_name,
                            ("release", "beta", "alpha"),
                        )
                    )
                except Exception as error:
                    label = dependency.file_name or dependency.project_id or dependency.version_id or "unknown dependency"
                    unresolved.append(f"{parent_label} requires Modrinth dependency {label}: {error}")
                    continue
                if dependency_version is None:
                    label = dependency.file_name or dependency.project_id or dependency.version_id or "unknown dependency"
                    unresolved.append(f"{parent_label} requires external dependency {label}, which has no provider project/version ID.")
                    continue
                if dependency_version.project_id in selected:
                    target = selected[dependency_version.project_id]
                    changed |= ModpackDependencyResolver._append_required_by(target, parent_label)
                    continue
                try:
                    ModrinthModInstaller._validate_version(dependency_version, instance.version_id, loader_name)
                    project = ModpackDependencyResolver._retry(lambda: ModrinthClient.get_project(dependency_version.project_id))
                    file = dependency_version.primary_file(".jar")
                except Exception as error:
                    unresolved.append(f"{parent_label} dependency {dependency_version.project_id} is not installable: {error}")
                    continue
                project_identities = ModpackDependencyResolver._project_identities(project)
                if project_identities & installed_identities:
                    queue.append((dependency_version, depth + 1, project.title or dependency_version.project_id))
                    continue
                if discovered >= ModpackDependencyResolver.MAX_DEPENDENCIES:
                    unresolved.append(f"The Modrinth dependency graph exceeds {ModpackDependencyResolver.MAX_DEPENDENCIES} added files.")
                    queue.clear()
                    break
                path = ModpackDependencyResolver._unique_mod_path(entries, file.filename, dependency_version.project_id, file.sha1)
                target = {
                    "path": path,
                    "fileName": PurePosixPath(path).name,
                    "sha1": file.sha1,
                    "sha512": file.sha512,
                    "size": file.size,
                    "source": "download",
                    "provider": "modrinth",
                    "projectId": dependency_version.project_id,
                    "versionId": dependency_version.version_id,
                    "versionNumber": dependency_version.version_number,
                    "downloads": [file.url] if file.url else [],
                    "required": True,
                    "selectionReason": "required_dependency",
                    "requiredBy": [parent_label],
                    "displayName": project.title,
                }
                entries.append(target)
                selected[dependency_version.project_id] = target
                installed_identities.update(project_identities)
                added.append(project.title or target["fileName"])
                discovered += 1
                changed = True
                queue.append((dependency_version, depth + 1, project.title or target["fileName"]))

        if changed or unresolved:
            registry["managedFiles"] = entries
            registry["dependencyResolution"] = ModpackDependencyResolver._resolution_payload(added, unresolved)
            registry["verificationCache"] = ModrinthPackRegistry._normalize_verification_cache(
                registry.get("verificationCache", {}), entries
            )
            ModrinthPackRegistry.save(instance.instance_dir, registry)
        return DependencyResolutionResult(tuple(added), tuple(warnings), tuple(unresolved))

    @staticmethod
    def _reconcile_pack_pinned_dependencies(instance: Instance, reporter: ProgressReporter | None) -> DependencyResolutionResult:
        if not getattr(instance, "instance_dir", None):
            return DependencyResolutionResult()
        registry = CurseForgePackRegistry.load(Path(instance.instance_dir))
        entries = [entry for entry in registry.get("managedFiles", []) if isinstance(entry, dict) and ModpackDependencyResolver._is_mod_entry(entry)]
        if not entries:
            return DependencyResolutionResult()
        try:
            mods = ModManager.list_mods(instance)
        except (AttributeError, FileNotFoundError, OSError):
            return DependencyResolutionResult()
        report = ModCompatibilityManager.scan(instance, mods=mods)
        issues = [issue for issue in report.issues if issue.code == "dependency-missing" and len(issue.mod_ids) >= 2]
        if not issues:
            return DependencyResolutionResult()

        entries_by_identity: dict[str, list[dict]] = {}
        changed = False
        for entry in entries:
            ModpackDependencyResolver._index_curseforge_entry_identities(entries_by_identity, entry)

        required_identities = {
            ModpackDependencyResolver._canonical_identity(issue.mod_ids[1])
            for issue in issues
            if len(issue.mod_ids) >= 2 and ModpackDependencyResolver._canonical_identity(issue.mod_ids[1])
        }
        missing_identities = required_identities - set(entries_by_identity)
        metadata_warning = ""
        if missing_identities:
            project_ids: set[int] = set()
            for entry in entries:
                try:
                    project_id = int(entry.get("projectId") or 0)
                except (TypeError, ValueError):
                    continue
                if project_id > 0:
                    project_ids.add(project_id)
            try:
                projects = ModpackDependencyResolver._retry(lambda: CurseForgeClient.get_projects_batch(project_ids)) if project_ids else {}
            except Exception as error:
                projects = {}
                metadata_warning = f"Could not refresh CurseForge project identities while reconciling pack-pinned dependencies: {error}"
            if projects:
                entries_by_identity.clear()
                for entry in entries:
                    try:
                        project_id = int(entry.get("projectId") or 0)
                    except (TypeError, ValueError):
                        project_id = 0
                    project = projects.get(project_id)
                    if project is not None:
                        project_name = str(getattr(project, "name", "") or "").strip()
                        project_slug = str(getattr(project, "slug", "") or "").strip().casefold()
                        if entry.get("projectName") != project_name:
                            entry["projectName"] = project_name
                            changed = True
                        if entry.get("projectSlug") != project_slug:
                            entry["projectSlug"] = project_slug
                            changed = True
                    ModpackDependencyResolver._index_curseforge_entry_identities(entries_by_identity, entry)

        parents_by_id = {mod.mod_id.casefold(): mod for mod in mods if mod.enabled and mod.mod_id and mod.mod_id != "unknown"}
        added: list[str] = []
        warnings: list[str] = [metadata_warning] if metadata_warning else []
        processed: set[tuple[str, str]] = set()
        ModpackDependencyResolver._report(reporter, "Reconciling pack-pinned mod dependencies...", 0, max(1, len(issues)))
        for completed, issue in enumerate(issues, start=1):
            parent_id = str(issue.mod_ids[0]).strip().casefold()
            dependency_id = str(issue.mod_ids[1]).strip().casefold()
            key = (parent_id, dependency_id)
            if not dependency_id or key in processed:
                ModpackDependencyResolver._report(reporter, "Reconciling pack-pinned mod dependencies...", completed, max(1, len(issues)))
                continue
            processed.add(key)
            candidates = entries_by_identity.get(ModpackDependencyResolver._canonical_identity(dependency_id), [])
            if len(candidates) != 1:
                ModpackDependencyResolver._report(reporter, "Reconciling pack-pinned mod dependencies...", completed, max(1, len(issues)))
                continue
            entry = candidates[0]
            expected = list(dict.fromkeys(str(value).strip().casefold() for value in entry.get("expectedModIds", []) if str(value).strip()))
            if dependency_id not in expected:
                expected.append(dependency_id)
                entry["expectedModIds"] = expected
                changed = True
            parent = parents_by_id.get(parent_id)
            parent_label = parent.name if parent is not None else parent_id
            changed |= ModpackDependencyResolver._append_required_by(entry, parent_label)

            target, _relative = CurseForgePackRegistry.managed_path(instance, str(entry.get("path") or ""), str(entry.get("fileName") or "dependency.jar"))
            provides_dependency = False
            if target.is_file():
                loader_name = str(ModLoaderManager.normalize(instance.mod_loader)[0]).strip().casefold()
                metadata = ModManager.read_mod(target, preferred_loader=loader_name, provider_version=str(entry.get("displayName") or ""))
                metadata = ModManager.apply_verified_curseforge_identity(instance, metadata, entry)
                identities = {metadata.mod_id.casefold()} | {mod_id.casefold() for mod_id, _version in metadata.provided_mods if mod_id}
                provides_dependency = dependency_id in identities
            if not provides_dependency:
                before = (bool(entry.get("pendingDownload", False)), bool(entry.get("retryableDownload", True)), str(entry.get("lastDownloadError") or ""))
                entry["pendingDownload"] = True
                entry["retryableDownload"] = True
                entry["lastDownloadError"] = f"Pack-pinned dependency '{dependency_id}' is missing or does not provide the expected mod ID."
                changed |= before != (True, True, entry["lastDownloadError"])
                label = str(entry.get("projectName") or entry.get("displayName") or entry.get("fileName") or dependency_id).strip()
                added.append(label)
            ModpackDependencyResolver._report(reporter, "Reconciling pack-pinned mod dependencies...", completed, max(1, len(issues)))

        if changed:
            registry["managedFiles"] = entries
            CurseForgePackRegistry.save(Path(instance.instance_dir), registry)
        return DependencyResolutionResult(tuple(dict.fromkeys(added)), tuple(dict.fromkeys(warnings)), ())

    @staticmethod
    def _index_curseforge_entry_identities(index: dict[str, list[dict]], entry: dict) -> None:
        expected = entry.get("expectedModIds", [])
        if isinstance(expected, str):
            expected = [expected]
        identities = {
            ModpackDependencyResolver._canonical_identity(entry.get("projectName")),
            ModpackDependencyResolver._canonical_identity(entry.get("projectSlug")),
            ModpackDependencyResolver._canonical_identity(entry.get("displayName")),
        }
        if isinstance(expected, (list, tuple, set)):
            identities.update(ModpackDependencyResolver._canonical_identity(value) for value in expected if str(value).strip())
        for identity in identities:
            if identity and entry not in index.setdefault(identity, []):
                index[identity].append(entry)

    @staticmethod
    def _resolve_curseforge(instance: Instance, registry: dict, reporter: ProgressReporter | None) -> DependencyResolutionResult:
        entries = [entry for entry in registry.get("managedFiles", []) if isinstance(entry, dict)]
        mod_entries = [entry for entry in entries if ModpackDependencyResolver._is_mod_entry(entry)]
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        loader_name = str(loader_name).strip().casefold()
        selected: dict[int, dict] = {}
        files: dict[int, CurseForgeFile] = {}
        warnings: list[str] = []
        unresolved: list[str] = []
        added: list[str] = []
        changed = False
        installed_identities = ModpackDependencyResolver._installed_mod_identities(instance)

        unresolved_file_ids: list[int] = []
        for entry in mod_entries:
            try:
                file_id = int(entry.get("fileId") or 0)
            except (TypeError, ValueError):
                file_id = 0
            if file_id > 0 and not bool(entry.get("dependencyMetadataResolved", False)):
                unresolved_file_ids.append(file_id)
        batch_files: dict[int, CurseForgeFile] = {}
        if unresolved_file_ids:
            try:
                batch_files = ModpackDependencyResolver._retry(lambda: CurseForgeClient.get_files_batch(unresolved_file_ids))
            except Exception as error:
                warnings.append(f"Could not batch-load CurseForge dependency metadata: {error}")

        ModpackDependencyResolver._report(reporter, "Resolving CurseForge modpack dependencies...", 0, max(1, len(mod_entries)))
        for completed, entry in enumerate(mod_entries, start=1):
            download_pause_controller.raise_if_requested()
            try:
                project_id = int(entry.get("projectId") or 0)
                file_id = int(entry.get("fileId") or 0)
            except (TypeError, ValueError):
                project_id = file_id = 0
            entry.setdefault("selectionReason", "pack_manifest")
            entry.setdefault("requiredBy", [])
            if project_id <= 0 or file_id <= 0:
                warnings.append(f"CurseForge file identity is unavailable: {entry.get('fileName') or entry.get('path')}")
                ModpackDependencyResolver._report(reporter, "Resolving CurseForge modpack dependencies...", completed, max(1, len(mod_entries)))
                continue
            try:
                if bool(entry.get("dependencyMetadataResolved", False)):
                    file = ModpackDependencyResolver._curseforge_file_from_entry(entry)
                else:
                    file = batch_files.get(file_id)
                    if file is None or file.project_id != project_id:
                        file = ModpackDependencyResolver._retry(lambda project_id=project_id, file_id=file_id: CurseForgeClient.get_file(project_id, file_id))
            except Exception as error:
                warnings.append(f"Could not load CurseForge dependency metadata for {entry.get('fileName')}: {error}")
                ModpackDependencyResolver._report(reporter, "Resolving CurseForge modpack dependencies...", completed, max(1, len(mod_entries)))
                continue
            changed |= ModpackDependencyResolver._hydrate_curseforge_entry(entry, file)
            selected.setdefault(project_id, entry)
            files[file_id] = file
            ModpackDependencyResolver._report(reporter, "Resolving CurseForge modpack dependencies...", completed, max(1, len(mod_entries)))

        queue: deque[tuple[CurseForgeFile, int, str]] = deque(
            (file, 0, ModpackDependencyResolver._entry_label(selected.get(file.project_id, {}), str(file.project_id)))
            for file in files.values()
        )
        visited_files: set[int] = set()
        discovered = 0

        while queue:
            file, depth, parent_label = queue.popleft()
            if file.file_id in visited_files:
                continue
            if depth > ModpackDependencyResolver.MAX_DEPTH:
                unresolved.append(f"CurseForge dependency depth exceeded {ModpackDependencyResolver.MAX_DEPTH} at {parent_label}.")
                continue
            visited_files.add(file.file_id)
            for dependency in file.dependencies:
                if not dependency.required:
                    continue
                download_pause_controller.raise_if_requested()
                if dependency.project_id in selected:
                    changed |= ModpackDependencyResolver._append_required_by(selected[dependency.project_id], parent_label)
                    continue
                try:
                    dependency_file = ModpackDependencyResolver._retry(
                        lambda dependency=dependency: CurseForgeClient.latest_compatible_file(
                            dependency.project_id,
                            instance.version_id,
                            loader=loader_name,
                            release_types=("release", "beta", "alpha"),
                        )
                    )
                except Exception as error:
                    unresolved.append(f"{parent_label} requires CurseForge project {dependency.project_id}: {error}")
                    continue
                if dependency_file.project_id in selected:
                    changed |= ModpackDependencyResolver._append_required_by(selected[dependency_file.project_id], parent_label)
                    continue
                if discovered >= ModpackDependencyResolver.MAX_DEPENDENCIES:
                    unresolved.append(f"The CurseForge dependency graph exceeds {ModpackDependencyResolver.MAX_DEPENDENCIES} added files.")
                    queue.clear()
                    break
                try:
                    project = ModpackDependencyResolver._retry(lambda: CurseForgeClient.get_project(dependency_file.project_id))
                    project_name = str(getattr(project, "name", "") or dependency_file.display_name).strip()
                    project_url = str(getattr(project, "project_url", "") or "").strip()
                except Exception:
                    project = None
                    project_name = dependency_file.display_name
                    project_url = ""
                project_identities = ModpackDependencyResolver._project_identities(project) if project is not None else {ModpackDependencyResolver._canonical_identity(project_name)}
                project_identities.discard("")
                if project_identities & installed_identities:
                    queue.append((dependency_file, depth + 1, project_name or dependency_file.file_name))
                    continue
                path = ModpackDependencyResolver._unique_mod_path(entries, dependency_file.file_name, str(dependency_file.project_id), dependency_file.sha1)
                target = {
                    "projectId": dependency_file.project_id,
                    "fileId": dependency_file.file_id,
                    "fileName": PurePosixPath(path).name,
                    "path": path,
                    "displayName": project_name or dependency_file.file_name,
                    "sha1": dependency_file.sha1,
                    "size": dependency_file.file_length,
                    "downloadUrl": dependency_file.download_url,
                    "declaredLoaders": list(dependency_file.loaders),
                    "gameVersions": list(dependency_file.game_versions),
                    "releaseType": dependency_file.release_type,
                    "datePublished": dependency_file.file_date,
                    "required": True,
                    "provider": "curseforge",
                    "pendingDownload": True,
                    "resolvePathFromProvider": False,
                    "selectionReason": "required_dependency",
                    "requiredBy": [parent_label],
                    "projectUrl": project_url,
                    "dependencies": [{"projectId": dependency.project_id, "relationType": dependency.relation_type} for dependency in dependency_file.dependencies],
                    "dependencyMetadataResolved": True,
                }
                entries.append(target)
                selected[dependency_file.project_id] = target
                installed_identities.update(project_identities)
                added.append(project_name or target["fileName"])
                discovered += 1
                changed = True
                queue.append((dependency_file, depth + 1, project_name or target["fileName"]))

        if changed or unresolved:
            registry["managedFiles"] = entries
            registry["dependencyResolution"] = ModpackDependencyResolver._resolution_payload(added, unresolved)
            CurseForgePackRegistry.save(Path(instance.instance_dir), registry)
        return DependencyResolutionResult(tuple(added), tuple(warnings), tuple(unresolved))

    @staticmethod
    def _resolve_cross_provider_missing(instance: Instance, reporter: ProgressReporter | None) -> DependencyResolutionResult:
        if not getattr(instance, "mod_loader", None) or not ModpackDependencyResolver._is_managed_modpack(instance):
            return DependencyResolutionResult()
        try:
            mods = ModManager.list_mods(instance)
        except (FileNotFoundError, OSError):
            return DependencyResolutionResult()
        report = ModCompatibilityManager.scan(instance, mods=mods)
        issues = [issue for issue in report.issues if issue.code == "dependency-missing" and len(issue.mod_ids) >= 2]
        if not issues:
            return DependencyResolutionResult()

        enabled_by_id: dict[str, list] = {}
        for mod in mods:
            if mod.enabled:
                enabled_by_id.setdefault(mod.mod_id.casefold(), []).append(mod)
        provenance = ModProvenanceRegistry.entries_by_file(instance)
        registry = ModrinthRegistry.load(instance)
        registry_mods = registry.setdefault("mods", {})
        selected_projects = {str(project_id).strip() for project_id in registry_mods if str(project_id).strip()}
        pack_registry = ModrinthPackRegistry.load(instance)
        selected_projects.update(
            str(entry.get("projectId") or "").strip()
            for entry in pack_registry.get("managedFiles", [])
            if isinstance(entry, dict) and str(entry.get("projectId") or "").strip()
        )
        installed_identities = {
            ModpackDependencyResolver._canonical_identity(identity)
            for mod in mods
            if mod.enabled
            for identity in ([mod.mod_id] if mod.mod_id != "unknown" else []) + [mod_id for mod_id, _version in mod.provided_mods]
            if ModpackDependencyResolver._canonical_identity(identity)
        }
        added: list[str] = []
        warnings: list[str] = []
        changed = False
        processed: set[tuple[str, str]] = set()

        ModpackDependencyResolver._report(reporter, "Resolving cross-provider mod dependencies...", 0, max(1, len(issues)))
        for completed, issue in enumerate(issues, start=1):
            parent_id = str(issue.mod_ids[0]).strip().casefold()
            dependency_id = str(issue.mod_ids[1]).strip().casefold()
            key = (parent_id, dependency_id)
            if not parent_id or not dependency_id or key in processed:
                ModpackDependencyResolver._report(reporter, "Resolving cross-provider mod dependencies...", completed, max(1, len(issues)))
                continue
            processed.add(key)
            parents = enabled_by_id.get(parent_id, [])
            for parent in parents:
                if not parent.managed_by_modpack or (parent.source_pack_provider or parent.source) != "curseforge":
                    continue
                source = provenance.get(parent.file_name.casefold(), {})
                sha1 = str(source.get("sha1") or "").strip().casefold() if isinstance(source, dict) else ""
                if not sha1:
                    sha1 = ModpackDependencyResolver._file_sha1(parent.path)
                if not sha1:
                    continue
                try:
                    mirror = ModpackDependencyResolver._retry(lambda sha1=sha1: ModrinthClient.get_version_from_hash(sha1, "sha1"))
                except Exception as error:
                    warnings.append(f"Could not enrich dependency metadata for {parent.name} through its exact file hash: {error}")
                    continue
                if mirror is None:
                    continue
                parent_label = parent.name or parent.file_name
                matched = False
                for dependency in mirror.dependencies:
                    if dependency.dependency_type != "required":
                        continue
                    try:
                        dependency_version = ModpackDependencyResolver._retry(
                            lambda dependency=dependency: ModrinthModInstaller._resolve_dependency(
                                dependency.version_id,
                                dependency.project_id,
                                instance.version_id,
                                str(ModLoaderManager.normalize(instance.mod_loader)[0]).strip().casefold(),
                                ("release", "beta", "alpha"),
                            )
                        )
                        if dependency_version is None:
                            continue
                        project = ModpackDependencyResolver._retry(lambda dependency_version=dependency_version: ModrinthClient.get_project(dependency_version.project_id))
                    except Exception as error:
                        warnings.append(f"Could not inspect a Modrinth mirror dependency for {parent_label}: {error}")
                        continue
                    if not ModpackDependencyResolver._project_matches_mod_id(project, dependency_id):
                        continue
                    matched = True
                    tree_result, tree_changed = ModpackDependencyResolver._append_modrinth_registry_tree(
                        instance=instance,
                        registry_mods=registry_mods,
                        selected_projects=selected_projects,
                        installed_identities=installed_identities,
                        root_version=dependency_version,
                        root_project=project,
                        parent_label=parent_label,
                        expected_mod_id=dependency_id,
                        pack_provider=parent.source_pack_provider or "curseforge",
                    )
                    added.extend(tree_result.added_files)
                    warnings.extend(tree_result.warnings)
                    changed |= tree_changed
                    break
                if matched:
                    break
            ModpackDependencyResolver._report(reporter, "Resolving cross-provider mod dependencies...", completed, max(1, len(issues)))

        if changed:
            ModrinthRegistry.save(instance, registry)
        return DependencyResolutionResult(tuple(added), tuple(warnings), ())

    @staticmethod
    def _append_modrinth_registry_tree(instance: Instance, registry_mods: dict, selected_projects: set[str], installed_identities: set[str], root_version: ModrinthVersion, root_project, parent_label: str, expected_mod_id: str, pack_provider: str) -> tuple[DependencyResolutionResult, bool]:
        queue: deque[tuple[ModrinthVersion, object, int, str, str]] = deque([(root_version, root_project, 0, parent_label, expected_mod_id)])
        visited: set[str] = set()
        added: list[str] = []
        warnings: list[str] = []
        changed = False
        discovered = 0
        loader_name = str(ModLoaderManager.normalize(instance.mod_loader)[0]).strip().casefold()

        while queue:
            version, project, depth, required_by, expected_id = queue.popleft()
            if version.version_id in visited:
                continue
            visited.add(version.version_id)
            if depth > ModpackDependencyResolver.MAX_DEPTH:
                warnings.append(f"Cross-provider dependency depth exceeded {ModpackDependencyResolver.MAX_DEPTH} at {required_by}.")
                continue
            project_id = version.project_id
            identities = ModpackDependencyResolver._project_identities(project)
            already_installed = bool(identities & installed_identities)
            entry = registry_mods.get(project_id)
            if isinstance(entry, dict):
                changed |= ModpackDependencyResolver._mark_registry_dependency(entry, required_by, pack_provider, expected_id)
            elif project_id not in selected_projects and not already_installed:
                if discovered >= ModpackDependencyResolver.MAX_DEPENDENCIES:
                    warnings.append(f"The cross-provider dependency graph exceeds {ModpackDependencyResolver.MAX_DEPENDENCIES} added files.")
                    break
                try:
                    ModrinthModInstaller._validate_version(version, instance.version_id, loader_name)
                    file = version.primary_file(".jar")
                except Exception as error:
                    warnings.append(f"{required_by} dependency {project_id} is not installable: {error}")
                    continue
                title = str(getattr(project, "title", "") or file.filename).strip()
                entry = {
                    "projectId": project_id,
                    "versionId": version.version_id,
                    "versionNumber": version.version_number,
                    "versionType": version.version_type,
                    "fileName": file.filename,
                    "sha1": file.sha1,
                    "sha512": file.sha512,
                    "size": file.size,
                    "downloadUrls": [file.url] if file.url else [],
                    "title": title,
                    "datePublished": version.date_published,
                    "pendingDownload": True,
                    "locked": True,
                    "managedByModpack": True,
                    "selectionReason": "required_dependency",
                    "requiredBy": [required_by],
                    "packProvider": pack_provider,
                }
                if expected_id:
                    entry["expectedModId"] = expected_id
                registry_mods[project_id] = entry
                selected_projects.add(project_id)
                installed_identities.update(identities)
                added.append(title)
                discovered += 1
                changed = True

            for dependency in version.dependencies:
                if dependency.dependency_type != "required":
                    continue
                try:
                    child_version = ModpackDependencyResolver._retry(
                        lambda dependency=dependency: ModrinthModInstaller._resolve_dependency(
                            dependency.version_id,
                            dependency.project_id,
                            instance.version_id,
                            loader_name,
                            ("release", "beta", "alpha"),
                        )
                    )
                    if child_version is None:
                        continue
                    child_project = ModpackDependencyResolver._retry(lambda child_version=child_version: ModrinthClient.get_project(child_version.project_id))
                except Exception as error:
                    warnings.append(f"Could not inspect required dependency metadata for {getattr(project, 'title', project_id)}: {error}")
                    continue
                queue.append((child_version, child_project, depth + 1, str(getattr(project, "title", "") or project_id), ""))

        return DependencyResolutionResult(tuple(added), tuple(warnings), ()), changed

    @staticmethod
    def _mark_registry_dependency(entry: dict, required_by: str, pack_provider: str, expected_mod_id: str = "") -> bool:
        before = dict(entry)
        entry["managedByModpack"] = True
        entry["selectionReason"] = "required_dependency"
        entry["packProvider"] = str(pack_provider or entry.get("packProvider") or "").strip().casefold()
        entry["locked"] = True
        if expected_mod_id:
            entry["expectedModId"] = expected_mod_id
        ModpackDependencyResolver._append_required_by(entry, required_by)
        return entry != before

    @staticmethod
    def _project_identities(project) -> set[str]:
        return {
            identity
            for identity in (
                ModpackDependencyResolver._canonical_identity(getattr(project, "slug", "")),
                ModpackDependencyResolver._canonical_identity(getattr(project, "title", "")),
                ModpackDependencyResolver._canonical_identity(getattr(project, "name", "")),
            )
            if identity
        }

    @staticmethod
    def _installed_mod_identities(instance: Instance) -> set[str]:
        try:
            mods = ModManager.list_mods(instance)
        except (AttributeError, FileNotFoundError, OSError):
            return set()
        return {
            identity
            for mod in mods
            if mod.enabled
            for raw in ([mod.mod_id] if mod.mod_id != "unknown" else []) + [mod_id for mod_id, _version in mod.provided_mods]
            if (identity := ModpackDependencyResolver._canonical_identity(raw))
        }

    @staticmethod
    def _prune_redundant_embedded_dependencies(instance: Instance) -> tuple[str, ...]:
        try:
            mods = ModManager.list_mods(instance)
        except (AttributeError, FileNotFoundError, OSError):
            return ()
        embedded_providers: dict[str, list] = {}
        for mod in mods:
            if not mod.enabled:
                continue
            for mod_id, _version in mod.provided_mods:
                normalized = str(mod_id or "").strip().casefold()
                if normalized:
                    embedded_providers.setdefault(normalized, []).append(mod)
        if not embedded_providers:
            return ()

        provenance = ModProvenanceRegistry.entries_by_file(instance)
        redundant = []
        for mod in mods:
            if not mod.enabled or mod.mod_id.casefold() not in embedded_providers:
                continue
            source = provenance.get(mod.file_name.casefold(), {})
            if not isinstance(source, dict) or str(source.get("selectionReason") or "").strip().casefold() != "required_dependency":
                continue
            providers = [provider for provider in embedded_providers[mod.mod_id.casefold()] if provider.path != mod.path]
            if providers:
                redundant.append((mod, providers[0]))
        if not redundant:
            return ()

        mods_dir = ModManager.mods_dir(instance).resolve()
        messages: list[str] = []
        removed: list[tuple[object, object]] = []
        for mod, provider in redundant:
            try:
                candidate = mod.path.resolve()
                if candidate.parent != mods_dir:
                    continue
                candidate.unlink(missing_ok=True)
                removed.append((mod, provider))
                messages.append(f"Removed redundant standalone dependency {mod.name}; {provider.name} already provides mod ID '{mod.mod_id}'.")
            except OSError:
                continue
        if not removed:
            return ()

        removed_names = [mod.file_name for mod, _provider in removed]
        filenames = {name.casefold() for name in removed_names}
        paths = {f"mods/{name}".replace("\\", "/").casefold() for name in removed_names}

        modrinth_pack = ModrinthPackRegistry.load(instance)
        mr_entries = [entry for entry in modrinth_pack.get("managedFiles", []) if isinstance(entry, dict)]
        filtered_mr = [entry for entry in mr_entries if str(entry.get("fileName") or PurePosixPath(str(entry.get("path") or "")).name).casefold() not in filenames and str(entry.get("path") or "").replace("\\", "/").casefold() not in paths]
        if filtered_mr != mr_entries:
            modrinth_pack["managedFiles"] = filtered_mr
            modrinth_pack["verificationCache"] = ModrinthPackRegistry._normalize_verification_cache(modrinth_pack.get("verificationCache", {}), filtered_mr)
            ModrinthPackRegistry.save(instance.instance_dir, modrinth_pack)

        curseforge_pack = CurseForgePackRegistry.load(Path(instance.instance_dir))
        cf_entries = [entry for entry in curseforge_pack.get("managedFiles", []) if isinstance(entry, dict)]
        filtered_cf = [entry for entry in cf_entries if str(entry.get("fileName") or PurePosixPath(str(entry.get("path") or "")).name).casefold() not in filenames and str(entry.get("path") or "").replace("\\", "/").casefold() not in paths]
        if filtered_cf != cf_entries:
            curseforge_pack["managedFiles"] = filtered_cf
            CurseForgePackRegistry.save(Path(instance.instance_dir), curseforge_pack)

        direct_registry = ModrinthRegistry.load(instance)
        direct_mods = direct_registry.get("mods") if isinstance(direct_registry.get("mods"), dict) else {}
        filtered_direct = {project_id: entry for project_id, entry in direct_mods.items() if not isinstance(entry, dict) or str(entry.get("fileName") or "").casefold() not in filenames}
        if filtered_direct != direct_mods:
            direct_registry["mods"] = filtered_direct
            ModrinthRegistry.save(instance, direct_registry)

        ModProvenanceRegistry.remove_by_filenames(instance, removed_names)
        return tuple(messages)

    @staticmethod
    def _project_matches_mod_id(project, mod_id: str) -> bool:
        identity = ModpackDependencyResolver._canonical_identity(mod_id)
        return bool(identity and identity in ModpackDependencyResolver._project_identities(project))

    @staticmethod
    def _canonical_identity(value: object) -> str:
        return "".join(character for character in str(value or "").casefold() if character.isalnum())

    @staticmethod
    def _file_sha1(path: Path) -> str:
        try:
            digest = hashlib.sha1()
            with Path(path).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _modrinth_version_for_entry(entry: dict) -> ModrinthVersion | None:
        version_id = str(entry.get("versionId") or "").strip()
        if not version_id:
            downloads = entry.get("downloads") if isinstance(entry.get("downloads"), list) else []
            for url in downloads:
                identity = ModProvenanceRegistry._modrinth_identity_from_url(str(url))
                if identity is None:
                    continue
                project_id, version_id, remote_name = identity
                entry["projectId"] = str(entry.get("projectId") or project_id)
                entry["versionId"] = version_id
                entry["fileName"] = str(entry.get("fileName") or remote_name)
                break
        if version_id:
            return ModpackDependencyResolver._retry(lambda: ModrinthClient.get_version(version_id))
        for algorithm in ("sha512", "sha1"):
            value = str(entry.get(algorithm) or "").strip().casefold()
            if not value:
                continue
            version = ModpackDependencyResolver._retry(lambda value=value, algorithm=algorithm: ModrinthClient.get_version_from_hash(value, algorithm))
            if version is not None:
                return version
        return None

    @staticmethod
    def _hydrate_modrinth_entry(entry: dict, version: ModrinthVersion) -> bool:
        file = version.primary_file(".jar")
        updates = {
            "projectId": version.project_id,
            "versionId": version.version_id,
            "versionNumber": version.version_number,
            "sha1": str(entry.get("sha1") or file.sha1).casefold(),
            "sha512": str(entry.get("sha512") or file.sha512).casefold(),
            "size": max(0, int(entry.get("size", 0) or file.size)),
            "downloads": list(entry.get("downloads") or ([file.url] if file.url else [])),
        }
        changed = False
        for key, value in updates.items():
            if entry.get(key) != value:
                entry[key] = value
                changed = True
        return changed

    @staticmethod
    def _hydrate_curseforge_entry(entry: dict, file: CurseForgeFile) -> bool:
        updates = {
            "fileName": Path(str(entry.get("fileName") or file.file_name)).name,
            "displayName": str(entry.get("displayName") or file.display_name),
            "sha1": str(entry.get("sha1") or file.sha1).casefold(),
            "size": max(0, int(entry.get("size", 0) or file.file_length)),
            "downloadUrl": str(entry.get("downloadUrl") or file.download_url),
            "declaredLoaders": list(entry.get("declaredLoaders") or file.loaders),
            "gameVersions": list(entry.get("gameVersions") or file.game_versions),
            "releaseType": str(entry.get("releaseType") or file.release_type),
            "datePublished": str(entry.get("datePublished") or file.file_date),
            "dependencies": [{"projectId": dependency.project_id, "relationType": dependency.relation_type} for dependency in file.dependencies],
            "dependencyMetadataResolved": True,
        }
        changed = False
        for key, value in updates.items():
            if entry.get(key) != value:
                entry[key] = value
                changed = True
        return changed

    @staticmethod
    def _curseforge_file_from_entry(entry: dict) -> CurseForgeFile:
        dependencies = tuple(
            CurseForgeDependency(
                project_id=int(raw.get("projectId") or 0),
                relation_type=int(raw.get("relationType") or 0),
            )
            for raw in entry.get("dependencies", [])
            if isinstance(raw, dict) and int(raw.get("projectId") or 0) > 0 and int(raw.get("relationType") or 0) > 0
        )
        return CurseForgeFile(
            file_id=int(entry.get("fileId") or 0),
            project_id=int(entry.get("projectId") or 0),
            display_name=str(entry.get("displayName") or entry.get("fileName") or "Unknown file").strip(),
            file_name=Path(str(entry.get("fileName") or "download.jar")).name,
            release_type=str(entry.get("releaseType") or "release").strip().casefold(),
            file_date=str(entry.get("datePublished") or "").strip(),
            file_length=max(0, int(entry.get("size", 0) or 0)),
            download_url=str(entry.get("downloadUrl") or "").strip(),
            sha1=str(entry.get("sha1") or "").strip().casefold(),
            game_versions=tuple(str(value) for value in entry.get("gameVersions", []) if str(value).strip()),
            dependencies=dependencies,
            is_available=True,
            loaders=tuple(str(value).strip().casefold() for value in entry.get("declaredLoaders", []) if str(value).strip()),
        )

    @staticmethod
    def _append_required_by(entry: dict, parent: str) -> bool:
        existing = entry.get("requiredBy") if isinstance(entry.get("requiredBy"), list) else []
        normalized = list(dict.fromkeys(str(value).strip() for value in existing if str(value).strip()))
        if parent and parent not in normalized:
            normalized.append(parent)
        changed = entry.get("requiredBy") != normalized
        entry["requiredBy"] = normalized
        return changed

    @staticmethod
    def _unique_mod_path(entries: list[dict], filename: str, project_id: str, sha1: str) -> str:
        safe_name = Path(str(filename or "dependency.jar")).name or "dependency.jar"
        candidate = f"mods/{safe_name}"
        existing = {str(entry.get("path") or "").replace("\\", "/").casefold(): entry for entry in entries if isinstance(entry, dict)}
        current = existing.get(candidate.casefold())
        if current is None or (sha1 and str(current.get("sha1") or "").casefold() == sha1.casefold()):
            return candidate
        prefix = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in str(project_id)).strip("-") or "dependency"
        return f"mods/{prefix}-{safe_name}"

    @staticmethod
    def _entry_label(entry: dict, fallback: str) -> str:
        return str(entry.get("displayName") or entry.get("title") or entry.get("fileName") or fallback).strip()

    @staticmethod
    def _resolution_payload(added: list[str], unresolved: list[str]) -> dict:
        return {
            "status": "unresolved" if unresolved else "complete",
            "added": list(dict.fromkeys(added)),
            "unresolved": list(dict.fromkeys(unresolved)),
            "resolvedAt": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _retry(call: Callable[[], T]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, ModpackDependencyResolver.MAX_ATTEMPTS + 1):
            download_pause_controller.raise_if_requested()
            try:
                return call()
            except Exception as error:
                last_error = error
                lowered = str(error).casefold()
                if any(marker in lowered for marker in ("http 400", "http 401", "http 403", "http 404", "not available", "no allowed", "invalid", "unsupported")):
                    break
                decision = DownloadRetryPolicy.decide(error, attempt, ModpackDependencyResolver.MAX_ATTEMPTS)
                if not decision.retry:
                    break
                sleep(min(max(decision.delay_seconds, 0.0), 1.0))
        assert last_error is not None
        raise last_error

    @staticmethod
    def _is_mod_entry(entry: dict) -> bool:
        path = str(entry.get("path") or "").replace("\\", "/").strip().lstrip("/")
        pure = PurePosixPath(path)
        return len(pure.parts) >= 2 and pure.parts[0].casefold() == "mods" and pure.name.casefold().endswith(".jar")

    @staticmethod
    def _has_managed_mods(value: object) -> bool:
        return isinstance(value, list) and any(isinstance(entry, dict) and ModpackDependencyResolver._is_mod_entry(entry) for entry in value)

    @staticmethod
    def _is_managed_modpack(instance: Instance) -> bool:
        if getattr(instance, "instance_dir", None) is None:
            return False
        return bool(ModrinthPackRegistry.load(instance).get("managedFiles") or CurseForgePackRegistry.load(Path(instance.instance_dir)).get("managedFiles"))

    @staticmethod
    def _report(reporter: ProgressReporter | None, message: str, current: int, total: int) -> None:
        if reporter is not None:
            reporter.files(stage=ProgressStage.CHECKING_MODPACK, message=message, current=current, total=total)
