from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import VERSION_ID
from src.core.diagnostics.forge_diagnostics_manager import ForgeDiagnosticsManager
from src.core.diagnostics.quilt_diagnostics_manager import QuiltDiagnosticsManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.instance_health_manager import InstanceHealthManager
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.instance_status_manager import InstanceStatusManager
from src.core.instance.settings_manager import SettingsManager
from src.core.java.adoptium_client import AdoptiumClient
from src.core.java.java_diagnostics_manager import JavaDiagnosticsManager
from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.java_manager import JavaManager
from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.forge.forge_change_manager import ForgeChangeManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.progress.progress_reporter import ProgressReporter
from src.core.package.modpack_package_manager import ModpackPackageManager
from src.core.package.portable_content_manager import PortableContentManager
from src.core.optifine.optifine_manager import OptiFineManager
from src.core.repair.repair_service import RepairService
from src.core.runtime.instance_repair_manager import InstanceRepairManager
from src.core.runtime.game_runtime_manager import GameRuntimeManager
from src.models.instance.instance import Instance
from src.models.instance.instance_state import InstanceStatus
from src.models.instance.instance_health import InstanceHealthReport
from src.models.progress.progress_callback import ProgressCallback
from src.models.package.modpack_export import ModpackExportOptions
from src.models.optifine.optifine_models import OptiFineCompatibilityResult, OptiFineInstallMode, OptiFineInstallResult, OptiFineState, OptiFineVersion

from mcw_core.models import InstanceCreateRequest, InstanceRuntimeProfile


class LoaderService:
    VANILLA = ModLoaderManager.VANILLA
    FABRIC = ModLoaderManager.FABRIC
    FORGE = ModLoaderManager.FORGE
    NEOFORGE = ModLoaderManager.NEOFORGE
    QUILT = ModLoaderManager.QUILT
    AUTO = ModLoaderManager.AUTO
    MODDED_LOADERS = ModLoaderManager.MODDED_LOADERS
    FORGE_FAMILY = ModLoaderManager.FORGE_FAMILY

    @staticmethod
    def normalize(loader: object) -> tuple[str, str]:
        return ModLoaderManager.normalize(loader)

    @staticmethod
    def resolve(game_version: str, loader_name: str, loader_version: str = AUTO) -> tuple[str, str]:
        return ModLoaderManager.resolve(game_version, loader_name, loader_version)

    @staticmethod
    def prepare(game_version: str, loader_name: str, loader_version: str = AUTO, on_progress: ProgressCallback | None = None):
        version = VersionManager.load(game_version)
        resolved = ModLoaderManager.resolve(version.id, loader_name, loader_version)
        prepared = ModLoaderManager.prepare(version, *resolved, reporter=ProgressReporter(on_progress))
        return prepared, resolved


class InstanceService:
    def __init__(self, loaders: LoaderService | None = None) -> None:
        self.loaders = loaders or LoaderService()

    @staticmethod
    def list() -> list[Instance]:
        return InstanceManager.list_instances()

    @staticmethod
    def load(name: str) -> Instance:
        return InstanceManager.load(name)

    @staticmethod
    def list_running() -> list[object]:
        return InstanceRunLock.list_active()

    @staticmethod
    def is_running(instance: Instance) -> bool:
        return InstanceRunLock.is_active(instance)

    @staticmethod
    def kill(name: str) -> bool:
        instance = InstanceManager.load(name)
        return GameRuntimeManager.kill(instance)

    @staticmethod
    def status(instance: Instance | str) -> InstanceStatus:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return InstanceStatusManager.resolve(loaded)

    @staticmethod
    def list_statuses() -> list[InstanceStatus]:
        return InstanceStatusManager.list(InstanceManager.list_instances())

    @staticmethod
    def health(instance: Instance | str) -> InstanceHealthReport:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return InstanceHealthManager.scan(loaded)

    @staticmethod
    def list_health() -> list[InstanceHealthReport]:
        return InstanceHealthManager.list(InstanceManager.list_instances())

    @staticmethod
    def set_icon(name: str, source_path: Path) -> Instance:
        return InstanceManager.set_icon(name, Path(source_path))

    @staticmethod
    def reset_icon(name: str) -> Instance:
        return InstanceManager.reset_icon(name)

    @staticmethod
    def set_library_metadata(name: str, *, favorite: bool | None = None, group: str | None = None, tags: object | None = None) -> Instance:
        return InstanceManager.set_library_metadata(name, favorite=favorite, group=group, tags=tags)

    @staticmethod
    def runtime_profile(name: str) -> InstanceRuntimeProfile:
        instance = InstanceService.load(name)
        version = VersionManager.load(instance.version_id)
        settings = SettingsManager.load(instance)
        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        required_java_major = JavaMajorPolicy.required_for_minecraft(
            instance.version_id,
            (getattr(version, "java_version", None) or {}).get("majorVersion"),
        )
        configured_java_path = str(getattr(settings, "java_path", "") or "").strip()
        return InstanceRuntimeProfile(
            instance_name=instance.name,
            minecraft_version=instance.version_id,
            loader_name=loader_name,
            loader_version=loader_version,
            required_java_major=required_java_major,
            managed_java_major=JavaMajorPolicy.resolve(required_java_major),
            java_automatic=not bool(configured_java_path),
            configured_java_path=configured_java_path,
        )

    @staticmethod
    def set_java_runtime(name: str, java_path: str | Path | None) -> InstanceRuntimeProfile:
        instance = InstanceService.load(name)
        if InstanceService.is_running(instance):
            raise RuntimeError("Close Minecraft before changing this instance's Java runtime.")

        profile = InstanceService.runtime_profile(name)
        configured = str(java_path or "").strip()
        if configured:
            executable = JavaManager.normalize_executable(Path(configured))
            if not executable.is_file():
                raise RuntimeError(f"Java path does not exist: {executable}")
            actual_major = JavaManager.get_major_version(executable)
            if actual_major is None:
                raise RuntimeError(f"Unable to determine the Java version at: {executable}")
            accepted = JavaMajorPolicy.accepted_majors(profile.required_java_major)
            if actual_major not in accepted:
                expected = " or ".join(f"Java {major}" for major in accepted)
                raise RuntimeError(f"Java {actual_major} is incompatible with this Minecraft runtime. Required: {expected}.")
            configured = str(executable)

        SettingsManager.update_java_path(instance, configured)
        return InstanceRuntimeProfile(
            instance_name=profile.instance_name,
            minecraft_version=profile.minecraft_version,
            loader_name=profile.loader_name,
            loader_version=profile.loader_version,
            required_java_major=profile.required_java_major,
            managed_java_major=profile.managed_java_major,
            java_automatic=not bool(configured),
            configured_java_path=configured,
        )

    def create(self, request: InstanceCreateRequest) -> Instance:
        name = InstanceManager.validate_name(request.name)
        version_id = str(request.version_id).strip()
        if not version_id:
            raise ValueError("Minecraft version cannot be empty.")
        version = VersionManager.load(version_id)
        resolved = self.loaders.resolve(version.id, request.loader_name, request.loader_version)
        ModLoaderManager.prepare(version, *resolved, reporter=ProgressReporter(request.on_progress))
        return InstanceManager.create(name=name, version=version, mod_loader=resolved)

    def create_with_optifine(self, request: InstanceCreateRequest, source_path: Path, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO, on_optifine_progress: ProgressCallback | None = None) -> Instance:
        created: Instance | None = None
        try:
            created = self.create(request)
            OptiFineManager.install(created, Path(source_path), mode, ProgressReporter(on_optifine_progress))
            return created
        except Exception:
            if created is not None:
                try:
                    InstanceManager.delete_instance(created.name)
                except Exception:
                    pass
            raise

    def change_loader(self, name: str, loader_name: str, loader_version: str, on_progress: ProgressCallback | None = None) -> Instance:
        instance = self.load(name)
        if self.is_running(instance):
            raise RuntimeError("Close Minecraft before changing this instance's mod loader.")
        target_name, target_version = self.loaders.normalize((loader_name, loader_version))
        current_name, _ = self.loaders.normalize(instance.mod_loader)
        reporter = ProgressReporter(on_progress)
        if current_name in self.loaders.FORGE_FAMILY or target_name in self.loaders.FORGE_FAMILY:
            return ForgeChangeManager.change(instance, target_name, target_version, reporter=reporter)
        version = VersionManager.load(instance.version_id)
        resolved = self.loaders.resolve(version.id, target_name, target_version)
        ModLoaderManager.prepare(version, *resolved, reporter=reporter)
        return InstanceManager.set_mod_loader(name, resolved)

    def repair_loader(self, name: str, on_progress: ProgressCallback | None = None) -> Instance:
        instance = self.load(name)
        if self.is_running(instance):
            raise RuntimeError("Close Minecraft before repairing this instance's mod loader.")
        reporter = ProgressReporter(on_progress)
        version = ModLoaderManager.repair(instance, reporter=reporter)
        loader_name, _ = self.loaders.normalize(instance.mod_loader)
        if loader_name not in self.loaders.FORGE_FAMILY:
            DownloadLibraryManager.load(version, reporter=reporter)
        return instance

    def restore_previous_loader(self, name: str, on_progress: ProgressCallback | None = None) -> Instance:
        instance = self.load(name)
        if self.is_running(instance):
            raise RuntimeError("Close Minecraft before restoring the previous mod-loader installation.")
        return ForgeChangeManager.restore_previous(instance, reporter=ProgressReporter(on_progress))

    def export_loader_diagnostics(self, name: str, output_path: Path) -> Path:
        instance = self.load(name)
        loader_name, _ = self.loaders.normalize(instance.mod_loader)
        manager = QuiltDiagnosticsManager if loader_name == self.loaders.QUILT else ForgeDiagnosticsManager
        return manager.export(instance, Path(output_path), launcher_version=VERSION_ID)

    @staticmethod
    def repair(name: str, on_progress: ProgressCallback | None = None):
        return InstanceRepairManager.repair(InstanceManager.load(name), on_progress=on_progress)

    @staticmethod
    def scan_repair(name: str, mode: str, on_progress: ProgressCallback | None = None):
        return RepairService.scan(InstanceManager.load(name), mode=mode, on_progress=on_progress)

    @staticmethod
    def execute_repair(name: str, plan: object, on_progress: ProgressCallback | None = None):
        return RepairService.repair(InstanceManager.load(name), plan, on_progress=on_progress)

    @staticmethod
    def rename(source_name: str, target_name: str) -> Path:
        return InstanceManager.rename(source_name, target_name)

    @staticmethod
    def clone(source_name: str, target_name: str, include_saves: bool = False) -> Instance:
        return InstanceManager.clone(source_name=source_name, new_name=target_name, include_saves=include_saves)

    @staticmethod
    def delete(name: str) -> bool:
        return InstanceManager.delete_instance(name)

    @staticmethod
    def inspect_package(package_path: Path):
        return InstanceManager.inspect_import(Path(package_path))

    @staticmethod
    def import_package(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | None = None) -> Instance:
        return InstanceManager.import_instance(Path(package_path), on_progress, settings_override=settings_override)

    @staticmethod
    def export_package(name: str, output_path: Path, include_saves: bool = False, on_progress: ProgressCallback | None = None) -> Path:
        return InstanceManager.export(name, Path(output_path), include_saves, on_progress)

    @staticmethod
    def inspect_modpack_package(package_path: Path):
        return ModpackPackageManager.inspect(Path(package_path))

    @staticmethod
    def import_modpack_package(package_path: Path, on_progress: ProgressCallback | None = None, settings_override: dict | None = None, install_optional_files: bool = True, instance_name: str = "") -> Instance:
        return ModpackPackageManager.import_package(Path(package_path), settings_override=settings_override, install_optional_files=install_optional_files, on_progress=on_progress, instance_name=instance_name)

    @staticmethod
    def export_modpack(name: str, output_path: Path, mode: str, portable_mode: str = "smart", include_saves: bool = False, on_progress: ProgressCallback | None = None):
        instance = InstanceManager.load(name)
        options = ModpackExportOptions(mode=mode, portable_mode=portable_mode, include_saves=include_saves)
        return ModpackPackageManager.export(instance, Path(output_path), options, on_progress)

    @staticmethod
    def install_portable_manual_files(name: str, requirements: object, sources: object) -> dict[str, object]:
        instance = InstanceManager.load(name)
        installed = PortableContentManager.install_many(instance, tuple(requirements or ()), tuple(Path(source) for source in (sources or ())))
        return {"instanceName": instance.name, "installed": installed}



class OptiFineService:
    OFFICIAL_DOWNLOADS_URL = "https://optifine.net/downloads"

    @staticmethod
    def inspect_file(source_path: Path) -> OptiFineVersion:
        return OptiFineManager.inspect_file(Path(source_path))

    @staticmethod
    def state(instance: Instance | str) -> OptiFineState:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return OptiFineManager.state(loaded)

    @staticmethod
    def compatibility(instance: Instance | str, version: OptiFineVersion, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO) -> OptiFineCompatibilityResult:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return OptiFineManager.compatibility(loaded, version, mode)

    @staticmethod
    def install(instance: Instance | str, source_path: Path, mode: str | OptiFineInstallMode = OptiFineInstallMode.AUTO, on_progress: ProgressCallback | None = None) -> OptiFineInstallResult:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return OptiFineManager.install(loaded, Path(source_path), mode, ProgressReporter(on_progress))

    @staticmethod
    def repair(instance: Instance | str, on_progress: ProgressCallback | None = None) -> OptiFineInstallResult:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return OptiFineManager.repair(loaded, ProgressReporter(on_progress))

    @staticmethod
    def uninstall(instance: Instance | str) -> bool:
        loaded = instance if isinstance(instance, Instance) else InstanceManager.load(str(instance))
        return OptiFineManager.uninstall(loaded)

class JavaService:
    @staticmethod
    def scan(on_progress: ProgressCallback | None = None) -> list[object]:
        return JavaDiagnosticsManager.scan(reporter=ProgressReporter(on_progress))

    @staticmethod
    def latest_feature_release() -> int:
        return AdoptiumClient.normalize_feature_major(AdoptiumClient.get_latest_feature_release())

    @staticmethod
    def normalize_feature_major(major: int | str | None) -> int:
        return AdoptiumClient.normalize_feature_major(major)

    @staticmethod
    def install(major: int, on_progress: ProgressCallback | None = None, force: bool = True) -> Path:
        normalized = AdoptiumClient.normalize_feature_major(major)
        return JavaProvisioner.install_managed(normalized, reporter=ProgressReporter(on_progress), force=force)
