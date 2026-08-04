from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.instance.settings_manager import SettingsManager
from src.core.java.java_resolver import JavaResolver
from src.core.minecraft.asset_manager import AssetManager
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.minecraft.library_manager import DownloadLibraryManager
from src.core.minecraft.version_manager import VersionManager
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_stage import ProgressStage
from src.models.runtime.instance_repair_result import InstanceRepairResult


class InstanceRepairManager:
    REPORT_SCHEMA_VERSION = 1

    @classmethod
    def repair(cls, instance: Instance, on_progress: ProgressCallback | None = None) -> InstanceRepairResult:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError("Close Minecraft before repairing this instance.")

        reporter = ProgressReporter(on_progress)
        reporter.status(stage=ProgressStage.REPAIRING_INSTANCE, message=f"Preparing repair for '{instance.name}'...")
        VersionManifestManager.get()

        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        reporter.status(stage=ProgressStage.LOADING_VERSION, message=f"Refreshing Minecraft {instance.version_id} metadata...")
        if loader_name in ModLoaderManager.MODDED_LOADERS:
            version = ModLoaderManager.repair(instance, reporter)
        else:
            version = VersionManager.load(instance.version_id)

        reporter.status(stage=ProgressStage.DOWNLOADING_CLIENT, message="Verifying Minecraft client...")
        client_path = DownloadClientManager.load(version=version, reporter=reporter)

        natives_dir = Paths.natives(version)
        native_markers = natives_dir / ".extracted"
        if native_markers.exists():
            shutil.rmtree(native_markers)

        reporter.status(stage=ProgressStage.DOWNLOADING_LIBRARIES, message="Verifying libraries and rebuilding natives...")
        libraries = DownloadLibraryManager.load(version=version, reporter=reporter)

        reporter.status(stage=ProgressStage.DOWNLOADING_ASSETS, message="Performing full asset verification...")
        assets_root = AssetManager.load(version=version, reporter=reporter)

        reporter.status(stage=ProgressStage.SELECTING_JAVA, message="Checking Java runtime...")
        java_major = int(version.java_version.get("majorVersion") or 8)
        settings = SettingsManager.load(instance)
        preferred_java = str(getattr(settings, "java_path", "") or "").strip()
        java_path = JavaResolver.resolve(java_major, reporter, preferred_java) if preferred_java else JavaResolver.resolve(java_major, reporter)

        completed_at = datetime.now(timezone.utc).isoformat()
        result = InstanceRepairResult(
            instance_name=instance.name,
            minecraft_version=version.id,
            mod_loader=loader_name if loader_name == ModLoaderManager.VANILLA else f"{loader_name} {loader_version}",
            java_path=java_path,
            client_path=client_path,
            libraries_checked=len(libraries),
            assets_root=assets_root,
            natives_rebuilt=True,
            completed_at=completed_at,
        )
        cls._write_report(instance, result)
        reporter.status(stage=ProgressStage.FINISHED, message=f"Repair completed for '{instance.name}'.")
        return result

    @classmethod
    def _write_report(cls, instance: Instance, result: InstanceRepairResult) -> None:
        path = Paths.instance_repair_report(instance)
        payload = {"schema_version": cls.REPORT_SCHEMA_VERSION, **result.to_dict()}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(payload, indent=4, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
