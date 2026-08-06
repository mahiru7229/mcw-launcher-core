from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import json
import os
import shutil

from src.core.backup.instance_backup_manager import InstanceBackupManager
from src.core.curseforge.curseforge_content_manager import CurseForgeContentManager
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.settings_manager import SettingsManager
from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_resolver import JavaResolver
from src.core.java.java_selector import JavaSelector
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.minecraft.asset_index_manager import AssetIndexManager
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.mod.modpack_dependency_resolver import ModpackDependencyResolver
from src.core.modrinth.modrinth_content_manager import ModrinthContentManager
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_pack_repair_manager import ModrinthPackRepairManager
from src.core.progress.progress_reporter import ProgressReporter
from src.core.repair.verification_cache import VerificationCache
from src.models.instance.instance import Instance
from src.models.minecraft.version import Version
from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_stage import ProgressStage
from src.models.repair.repair_models import (
    RepairComponent,
    RepairComponentResult,
    RepairExecutionResult,
    RepairIssue,
    RepairMode,
    RepairPlan,
    RepairReport,
    RepairSeverity,
    RepairStatus,
)


class RepairService:
    REPORT_SCHEMA_VERSION = 1
    DEFAULT_COMPONENTS = tuple(RepairComponent)
    INSTANCE_SCOPED_COMPONENTS = frozenset({
        RepairComponent.MOD_LOADER,
        RepairComponent.MODPACK,
        RepairComponent.SETTINGS,
    })

    @classmethod
    def scan(cls, instance: Instance, mode: RepairMode | str = RepairMode.QUICK, components: Iterable[RepairComponent | str] | None = None, on_progress: ProgressCallback | None = None) -> RepairReport:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before checking or repairing this instance.")

        normalized_mode = cls._mode(mode)
        selected = cls._components(components)
        reporter = ProgressReporter(on_progress)
        started_at = cls._now()
        scan_stage = ProgressStage.VERIFYING_REPAIR if normalized_mode is RepairMode.FULL else ProgressStage.SCANNING_REPAIR
        reporter.steps(scan_stage, f"Preparing {normalized_mode.value} instance check...", 0, max(1, len(selected)))

        base_version = cls._load_base_version(instance)
        scan_version, loader_issue = cls._version_for_scan(instance, base_version)
        cache = VerificationCache(Paths.instance_repair_cache(instance))
        results: list[RepairComponentResult] = []

        scanners = {
            RepairComponent.CLIENT: lambda: cls._scan_client(scan_version, cache, normalized_mode),
            RepairComponent.LIBRARIES: lambda: cls._scan_libraries(scan_version, cache, normalized_mode),
            RepairComponent.ASSETS: lambda: cls._scan_assets(scan_version, cache, normalized_mode),
            RepairComponent.JAVA: lambda: cls._scan_java(instance, scan_version),
            RepairComponent.MOD_LOADER: lambda: cls._scan_loader(instance, loader_issue),
            RepairComponent.MODPACK: lambda: cls._scan_modpack(instance, cache, normalized_mode, reporter),
            RepairComponent.LAN_AGENT: lambda: cls._scan_lan_agent(instance),
            RepairComponent.SETTINGS: lambda: cls._scan_settings(instance),
        }

        try:
            for index, component in enumerate(selected, start=1):
                reporter.steps(scan_stage, f"Checking {component.value.replace('_', ' ')}...", index - 1, len(selected))
                try:
                    result = scanners[component]()
                except Exception as error:
                    issue = RepairIssue(
                        component=component,
                        code="scan_failed",
                        message=str(error),
                        severity=RepairSeverity.ERROR,
                        repairable=component not in {RepairComponent.SETTINGS},
                    )
                    result = RepairComponentResult(component=component, status=RepairStatus.FAILED, issues=(issue,), detail=str(error))
                results.append(result)
                reporter.steps(scan_stage, f"Checked {component.value.replace('_', ' ')}.", index, len(selected))
        finally:
            cache.save()

        report = RepairReport(
            instance_name=instance.name,
            mode=normalized_mode,
            components=tuple(results),
            started_at=started_at,
            completed_at=cls._now(),
        )
        cls._write_json(Paths.instance_repair_scan_report(instance), {"schema_version": cls.REPORT_SCHEMA_VERSION, **report.to_dict()})
        reporter.succeeded(scan_stage, f"{normalized_mode.value.title()} instance check completed.")
        return report

    @classmethod
    def build_plan(cls, report: RepairReport, components: Iterable[RepairComponent | str] | None = None) -> RepairPlan:
        selected = cls._components(components) if components is not None else tuple(component.component for component in report.components)
        selected_set = set(selected)
        issues = tuple(issue for issue in report.issues if issue.component in selected_set)
        return RepairPlan(
            instance_name=report.instance_name,
            report=report,
            selected_components=selected,
            issues=issues,
            estimated_download_bytes=sum(max(0, issue.download_bytes) for issue in issues if issue.repairable),
            requires_manual_action=any(issue.manual_action for issue in issues),
        )

    @classmethod
    def repair(cls, instance: Instance, plan: RepairPlan, on_progress: ProgressCallback | None = None) -> RepairExecutionResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before checking or repairing this instance.")
        if plan.instance_name != instance.name:
            raise RuntimeError("The repair plan belongs to a different instance.")

        reporter = ProgressReporter(on_progress)
        selected = tuple(dict.fromkeys(plan.selected_components))
        reporter.steps(ProgressStage.APPLYING_REPAIR, f"Preparing repair for '{instance.name}'...", 0, max(1, len(selected)))
        repaired: list[RepairComponent] = []
        failed: list[RepairComponent] = []
        warnings: list[str] = []
        backup_path: Path | None = None
        rolled_back = False
        rollback_error = ""
        repairable_components = {issue.component for issue in plan.repairable_issues}
        protected_components = set(selected) & repairable_components & set(cls.INSTANCE_SCOPED_COMPONENTS)

        if protected_components:
            reporter.steps(
                ProgressStage.APPLYING_REPAIR,
                f"Creating a recovery point for '{instance.name}'...",
                0,
                max(1, len(selected)),
            )
            backup_path = InstanceBackupManager.create(
                instance,
                InstanceBackupManager.SCOPE_FULL,
                reason="pre-repair-center",
            ).backup.path

        for index, component in enumerate(selected, start=1):
            component_issues = tuple(issue for issue in plan.issues if issue.component is component)
            if not component_issues:
                reporter.steps(ProgressStage.APPLYING_REPAIR, f"Skipping healthy {component.value.replace('_', ' ')}.", index, len(selected))
                continue
            repairable_issues = tuple(issue for issue in component_issues if issue.repairable)
            if not repairable_issues:
                warnings.extend(issue.message for issue in component_issues)
                reporter.steps(
                    ProgressStage.APPLYING_REPAIR,
                    f"Skipping {component.value.replace('_', ' ')}; manual action is required.",
                    index,
                    len(selected),
                )
                continue
            reporter.steps(ProgressStage.APPLYING_REPAIR, f"Repairing {component.value.replace('_', ' ')}...", index - 1, len(selected))
            try:
                cls._repair_component(instance, component, reporter)
                repaired.append(component)
            except Exception as error:
                failed.append(component)
                warnings.append(f"{component.value}: {error}")
            reporter.steps(ProgressStage.APPLYING_REPAIR, f"Processed {component.value.replace('_', ' ')}.", index, len(selected))

        if backup_path is not None and any(component in protected_components for component in failed):
            try:
                InstanceBackupManager.restore(instance, backup_path, create_safety_backup=False)
                rolled_back = True
                repaired = [component for component in repaired if component not in protected_components]
                warnings.append("Instance-scoped repair changes were rolled back to the recovery point.")
            except Exception as error:
                rollback_error = str(error)
                warnings.append(f"Recovery point restore failed: {error}")

        # Re-check only repaired components. Full verification confirms that the
        # downloader did not merely recreate a same-sized corrupted file.
        verification_components = tuple(component for component in repaired if component not in failed)
        verification = None
        if verification_components:
            verification = cls.scan(instance, RepairMode.FULL, verification_components, on_progress)
            for component_result in verification.components:
                if component_result.status in {RepairStatus.BROKEN, RepairStatus.FAILED}:
                    if component_result.component not in failed:
                        failed.append(component_result.component)
                    warnings.extend(issue.message for issue in component_result.issues)

        report_path = Paths.instance_repair_execution_report(instance)
        result = RepairExecutionResult(
            instance_name=instance.name,
            selected_components=selected,
            repaired_components=tuple(component for component in repaired if component not in failed),
            failed_components=tuple(dict.fromkeys(failed)),
            warnings=tuple(dict.fromkeys(warnings)),
            checked_files=verification.checked_files if verification is not None else plan.report.checked_files,
            repaired_issues=sum(
                1
                for issue in plan.repairable_issues
                if issue.component in repaired and issue.component not in failed
            ),
            completed_at=cls._now(),
            report_path=report_path,
            backup_path=backup_path,
            rolled_back=rolled_back,
            rollback_error=rollback_error,
        )
        cls._write_json(report_path, {"schema_version": cls.REPORT_SCHEMA_VERSION, **result.to_dict()})
        if result.failed_components:
            detail = "\n".join(result.warnings)
            reporter.failed(ProgressStage.APPLYING_REPAIR, "Repair completed with unresolved problems.", detail)
        else:
            reporter.succeeded(ProgressStage.APPLYING_REPAIR, "Repair completed successfully.")
        return result

    @classmethod
    def _scan_client(cls, version: Version, cache: VerificationCache, mode: RepairMode) -> RepairComponentResult:
        client = DownloadClientManager._load_download_object(version.raw_json)
        path = Paths.client(version)
        result = cache.verify("client:" + str(path), path, client.size, client.sha1, "sha1", force_hash=mode is RepairMode.FULL)
        issues: list[RepairIssue] = []
        if not result.valid:
            issues.append(cls._file_issue(RepairComponent.CLIENT, "client_" + result.reason, path, client.sha1, client.size, client.size))
        return cls._result(RepairComponent.CLIENT, 1, result.cache_hit, result.hashed, issues, "Minecraft client is ready." if not issues else "Minecraft client needs repair.")

    @classmethod
    def _scan_libraries(cls, version: Version, cache: VerificationCache, mode: RepairMode) -> RepairComponentResult:
        libraries = DownloadLibraryManager._load_download_object(version.raw_json)
        issues: list[RepairIssue] = []
        cache_hits = 0
        hashed = 0
        for library in libraries:
            path = Paths.libraries() / library.path
            result = cache.verify("library:" + library.path.as_posix(), path, library.size, library.sha1, "sha1", force_hash=mode is RepairMode.FULL)
            cache_hits += int(result.cache_hit)
            hashed += int(result.hashed)
            if not result.valid:
                issues.append(cls._file_issue(RepairComponent.LIBRARIES, "library_" + result.reason, path, library.sha1, library.size, library.size))
        return cls._result(RepairComponent.LIBRARIES, len(libraries), cache_hits, hashed, issues, f"Checked {len(libraries)} Minecraft libraries.")

    @classmethod
    def _scan_assets(cls, version: Version, cache: VerificationCache, mode: RepairMode) -> RepairComponentResult:
        issues: list[RepairIssue] = []
        cache_hits = 0
        hashed = 0
        checked = 0
        index_info = AssetIndexManager._parse_assets_index(version)
        index_path = Paths.asset_index(version)
        index_result = cache.verify("asset-index:" + str(index_path), index_path, index_info.size, index_info.sha1, "sha1", force_hash=mode is RepairMode.FULL)
        checked += 1
        cache_hits += int(index_result.cache_hit)
        hashed += int(index_result.hashed)
        if not index_result.valid:
            issues.append(cls._file_issue(RepairComponent.ASSETS, "asset_index_" + index_result.reason, index_path, index_info.sha1, index_info.size, index_info.size))
            return cls._result(RepairComponent.ASSETS, checked, cache_hits, hashed, issues, "Asset index is missing or invalid; object verification is unavailable until it is repaired.")

        assets_data = AssetManager._load_asset_index(index_path)
        assets = AssetManager._parse_assets(assets_data)
        for asset in assets:
            path = Paths.asset_object(asset)
            result = cache.verify("asset:" + asset.sha1, path, asset.size, asset.sha1, "sha1", force_hash=mode is RepairMode.FULL)
            checked += 1
            cache_hits += int(result.cache_hit)
            hashed += int(result.hashed)
            if not result.valid:
                issues.append(cls._file_issue(RepairComponent.ASSETS, "asset_" + result.reason, path, asset.sha1, asset.size, asset.size))
        return cls._result(RepairComponent.ASSETS, checked, cache_hits, hashed, issues, f"Checked {len(assets)} asset objects and the asset index.")

    @classmethod
    def _scan_java(cls, instance: Instance, version: Version) -> RepairComponentResult:
        required_major = int((version.java_version or {}).get("majorVersion") or 8)
        managed_major = JavaMajorPolicy.resolve(required_major)
        settings = SettingsManager.load(instance)
        preferred_path = getattr(settings, "java_path", "")
        try:
            if str(preferred_path or "").strip():
                path = JavaResolver.resolve(required_major, preferred_path=preferred_path)
            else:
                path = JavaSelector.select_java(managed_major)
        except RuntimeError as error:
            issue = RepairIssue(
                component=RepairComponent.JAVA,
                code="java_missing",
                message=str(error),
                severity=RepairSeverity.ERROR,
                repairable=True,
            )
            return cls._result(RepairComponent.JAVA, 0, 0, 0, [issue], f"Java {managed_major} is not ready.")
        return cls._result(RepairComponent.JAVA, 1, 0, 0, [], f"Java {managed_major} is available at {path}.")

    @classmethod
    def _scan_loader(cls, instance: Instance, loader_issue: RepairIssue | None) -> RepairComponentResult:
        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name == ModLoaderManager.VANILLA:
            return cls._result(RepairComponent.MOD_LOADER, 0, 0, 0, [], "Vanilla does not require a separate mod-loader profile.")
        issues = [loader_issue] if loader_issue is not None else []
        detail = f"{loader_name.title()} {loader_version} profile is ready." if not issues else f"{loader_name.title()} {loader_version} profile needs repair."
        return cls._result(RepairComponent.MOD_LOADER, 1, 0, 0, issues, detail)

    @classmethod
    def _scan_modpack(cls, instance: Instance, cache: VerificationCache, mode: RepairMode, reporter: ProgressReporter) -> RepairComponentResult:
        issues: list[RepairIssue] = []
        checked = 0
        cache_hits = 0
        hashed = 0

        modrinth = ModrinthPackRegistry.load(instance)
        if modrinth:
            state = ModrinthPackRegistry.scan(instance, reporter=reporter, force_hash=mode is RepairMode.FULL)
            checked += state.managed_files
            cache_hits += state.cache_hits
            hashed += state.hashed_files
            for change in state.changes:
                path = Path(instance.instance_dir) / change.path
                issues.append(RepairIssue(
                    component=RepairComponent.MODPACK,
                    code=f"modrinth_{change.state}",
                    message=f"Modrinth managed file is {change.state}: {change.path}",
                    severity=RepairSeverity.ERROR,
                    repairable=True,
                    path=path,
                ))

        curseforge = CurseForgePackRegistry.load(instance)
        for entry in curseforge.get("managedFiles", []) if curseforge else []:
            if not isinstance(entry, dict):
                continue
            target, relative = CurseForgePackRegistry.managed_path(instance, str(entry.get("path") or ""), str(entry.get("fileName") or "download.bin"))
            expected_size = int(entry.get("size", 0) or 0)
            expected_hash = str(entry.get("sha1") or "")
            result = cache.verify("curseforge-pack:" + relative.casefold(), target, expected_size, expected_hash, "sha1", force_hash=mode is RepairMode.FULL)
            checked += 1
            cache_hits += int(result.cache_hit)
            hashed += int(result.hashed)
            if not result.valid:
                retryable = bool(entry.get("retryableDownload", True))
                manual = not retryable or bool(entry.get("lastDownloadError")) and "manual" in str(entry.get("lastDownloadError")).casefold()
                issues.append(RepairIssue(
                    component=RepairComponent.MODPACK,
                    code="curseforge_" + result.reason,
                    message=f"CurseForge managed file is missing or invalid: {relative}",
                    severity=RepairSeverity.ERROR,
                    repairable=retryable,
                    path=target,
                    expected_hash=expected_hash,
                    expected_size=expected_size,
                    download_bytes=expected_size,
                    manual_action=manual,
                ))

        if not modrinth and not curseforge:
            return cls._result(RepairComponent.MODPACK, 0, 0, 0, [], "This instance is not managed by a Modrinth or CurseForge modpack.")
        return cls._result(RepairComponent.MODPACK, checked, cache_hits, hashed, issues, f"Checked {checked} managed modpack files.")

    @classmethod
    def _scan_lan_agent(cls, instance: Instance) -> RepairComponentResult:
        settings = SettingsManager.load(instance)
        if not LanAgentManager.is_enabled(settings.lan_auth_mode):
            return cls._result(RepairComponent.LAN_AGENT, 0, 0, 0, [], "Private Offline LAN is disabled for this instance.")
        path = LanAgentManager.runtime_agent_path()
        try:
            LanAgentManager._verify_file(path, "MCW LAN Agent")
        except RuntimeError as error:
            issue = RepairIssue(
                component=RepairComponent.LAN_AGENT,
                code="lan_agent_invalid",
                message=str(error),
                severity=RepairSeverity.ERROR,
                repairable=True,
                path=path,
            )
            return cls._result(RepairComponent.LAN_AGENT, 1, 0, 0, [issue], "MCW LAN Agent needs repair.")
        return cls._result(RepairComponent.LAN_AGENT, 1, 0, 0, [], "MCW LAN Agent checksum is valid.")

    @classmethod
    def _scan_settings(cls, instance: Instance) -> RepairComponentResult:
        path = Paths.instance_settings_path(instance)
        issues: list[RepairIssue] = []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings.json root is not an object")
            SettingsManager._parse_instance_settings(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            issues.append(RepairIssue(
                component=RepairComponent.SETTINGS,
                code="settings_invalid",
                message=f"Instance settings are invalid: {error}",
                severity=RepairSeverity.ERROR,
                repairable=True,
                path=path,
            ))
        metadata_path = Path(instance.instance_dir) / "instance.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or not str(metadata.get("name") or "").strip():
                raise ValueError("instance.json is missing required metadata")
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            issues.append(RepairIssue(
                component=RepairComponent.SETTINGS,
                code="metadata_invalid",
                message=f"Instance metadata are invalid: {error}",
                severity=RepairSeverity.ERROR,
                repairable=False,
                path=metadata_path,
            ))
        return cls._result(RepairComponent.SETTINGS, 2, 0, 0, issues, "Checked instance settings and metadata.")

    @classmethod
    def _repair_component(cls, instance: Instance, component: RepairComponent, reporter: ProgressReporter) -> None:
        if component is RepairComponent.MOD_LOADER:
            loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
            if loader_name != ModLoaderManager.VANILLA:
                ModLoaderManager.repair(instance, reporter=reporter)
            return

        if component is RepairComponent.SETTINGS:
            settings = SettingsManager.load(instance)
            SettingsManager.save(instance, settings)
            return

        if component is RepairComponent.LAN_AGENT:
            LanAgentManager.install()
            return

        if component is RepairComponent.MODPACK:
            if ModrinthPackRegistry.load(instance):
                ModrinthPackRepairManager.repair(instance, reporter=reporter)
            if CurseForgePackRegistry.load(instance):
                CurseForgeContentManager.ensure(instance, reporter=reporter, block_launch_on_failure=True)
            final_resolution = ModpackDependencyResolver.resolve(instance, reporter)
            for _pass_number in range(ModpackDependencyResolver.MAX_COMPLETION_PASSES):
                if not final_resolution.changed:
                    break
                ModrinthContentManager.ensure(instance, reporter=reporter, block_launch_on_failure=True)
                CurseForgeContentManager.ensure(instance, reporter=reporter, block_launch_on_failure=True)
                final_resolution = ModpackDependencyResolver.resolve(instance, reporter)
            if final_resolution.changed:
                ModrinthContentManager.ensure(instance, reporter=reporter, block_launch_on_failure=True)
                CurseForgeContentManager.ensure(instance, reporter=reporter, block_launch_on_failure=True)
                final_resolution = ModpackDependencyResolver.resolve(instance, reporter)
            ModpackDependencyResolver.raise_for_required_dependencies(instance, final_resolution.unresolved)
            return

        # Core Minecraft repairs share one resolved runtime profile. The loader
        # itself is not force-refreshed unless MOD_LOADER was explicitly selected.
        version = ModLoaderManager.load(instance, reporter=reporter)
        if component is RepairComponent.CLIENT:
            DownloadClientManager.load(version, reporter=reporter)
            return
        if component is RepairComponent.LIBRARIES:
            marker = Paths.natives(version) / ".extracted"
            if marker.exists():
                shutil.rmtree(marker, ignore_errors=True)
            DownloadLibraryManager.load(version, reporter=reporter)
            return
        if component is RepairComponent.ASSETS:
            AssetManager.load(version, reporter=reporter)
            return
        if component is RepairComponent.JAVA:
            major = int((version.java_version or {}).get("majorVersion") or 8)
            settings = SettingsManager.load(instance)
            preferred_java = str(getattr(settings, "java_path", "") or "").strip()
            if preferred_java:
                JavaResolver.resolve(major, reporter, preferred_java)
            else:
                JavaResolver.resolve(major, reporter)
            return
        raise RuntimeError(f"Unsupported repair component: {component.value}")

    @classmethod
    def _load_base_version(cls, instance: Instance) -> Version:
        cached_path = Paths.CACHE_ROOT / "versions" / instance.version_id / f"{instance.version_id}.json"
        try:
            cached_data = json.loads(cached_path.read_text(encoding="utf-8"))
            cached_version = VersionManager._parse_version(cached_data, cached_path)
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            cached_version = None

        try:
            return VersionManager.load(instance.version_id)
        except RuntimeError:
            if cached_version is not None:
                return cached_version
            raise

    @classmethod
    def _version_for_scan(cls, instance: Instance, base_version: Version) -> tuple[Version, RepairIssue | None]:
        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        if loader_name == ModLoaderManager.VANILLA:
            return base_version, None
        if loader_name == ModLoaderManager.FABRIC:
            path = Paths.fabric_version_json(base_version.id, loader_version)
        elif loader_name == ModLoaderManager.FORGE:
            path = Paths.forge_version_json(base_version.id, loader_version)
        elif loader_name == ModLoaderManager.NEOFORGE:
            path = Paths.neoforge_version_json(base_version.id, loader_version)
        elif loader_name == ModLoaderManager.QUILT:
            path = Paths.quilt_version_json(base_version.id, loader_version)
        else:
            issue = RepairIssue(
                component=RepairComponent.MOD_LOADER,
                code="loader_unsupported",
                message=f"Unsupported mod loader: {loader_name}",
                severity=RepairSeverity.ERROR,
                repairable=False,
            )
            return base_version, issue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            version = VersionManager._parse_version(data, path)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            version = None
        if version is not None:
            return version, None
        issue = RepairIssue(
            component=RepairComponent.MOD_LOADER,
            code="loader_profile_missing",
            message=f"{loader_name.title()} {loader_version} profile is missing or invalid.",
            severity=RepairSeverity.ERROR,
            repairable=True,
            path=path,
        )
        return base_version, issue

    @staticmethod
    def _file_issue(component: RepairComponent, code: str, path: Path, expected_hash: str, expected_size: int, download_bytes: int) -> RepairIssue:
        reason = code.rsplit("_", 1)[-1].replace("_", " ")
        return RepairIssue(
            component=component,
            code=code,
            message=f"{path.name} is {reason}.",
            severity=RepairSeverity.ERROR,
            repairable=True,
            path=path,
            expected_hash=expected_hash,
            expected_size=expected_size,
            download_bytes=max(0, download_bytes),
        )

    @staticmethod
    def _result(component: RepairComponent, checked: int, cache_hits: int, hashed: int, issues: list[RepairIssue], detail: str) -> RepairComponentResult:
        if any(issue.severity is RepairSeverity.ERROR for issue in issues):
            status = RepairStatus.BROKEN
        elif issues:
            status = RepairStatus.WARNING
        else:
            status = RepairStatus.HEALTHY
        return RepairComponentResult(
            component=component,
            status=status,
            checked_files=checked,
            cache_hits=cache_hits,
            hashed_files=hashed,
            issues=tuple(issues),
            detail=detail,
        )

    @classmethod
    def _components(cls, components: Iterable[RepairComponent | str] | None) -> tuple[RepairComponent, ...]:
        if components is None:
            return cls.DEFAULT_COMPONENTS
        normalized: list[RepairComponent] = []
        for component in components:
            parsed = component if isinstance(component, RepairComponent) else RepairComponent(str(component))
            if parsed not in normalized:
                normalized.append(parsed)
        return tuple(normalized)

    @staticmethod
    def _mode(mode: RepairMode | str) -> RepairMode:
        return mode if isinstance(mode, RepairMode) else RepairMode(str(mode).strip().lower())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
