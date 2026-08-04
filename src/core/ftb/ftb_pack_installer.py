from __future__ import annotations

from pathlib import PurePosixPath
import re

from src.core.ftb.ftb_client import FTBClient
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.network.download_pause import download_pause_controller
from src.core.progress.progress_reporter import ProgressReporter
from src.models.ftb.install_result import FTBModpackInstallResult
from src.models.ftb.version import FTBFile, FTBVersion
from src.models.progress.progress_stage import ProgressStage


class FTBPackInstaller:
    MAX_FILES = 20_000
    MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024
    MAX_PATH_LENGTH = 240
    RESERVED_ROOT_NAMES = {"instance.json", "settings.json", ".mcw"}
    INSTANCE_NAME_PATTERN = re.compile(r'^[^<>:"/\\|?*\x00-\x1F]{1,80}$')
    SUPPORTED_LOADERS = frozenset(ModLoaderManager.MODDED_LOADERS)

    @staticmethod
    def install(project_id: int, version_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> FTBModpackInstallResult:
        name = FTBPackInstaller._validated_instance_name(instance_name)
        if InstanceManager.is_instance_exist(name):
            raise RuntimeError(f"Instance '{name}' already exists.")
        allowed = FTBClient._normalized_release_types(allowed_release_types)
        project = FTBClient.get_project(project_id)
        version = FTBClient.get_version(project_id, version_id)
        if version.release_type not in allowed:
            raise RuntimeError(f"FTB modpack version '{version.name}' uses the disabled {version.release_type} channel.")
        minecraft_version, loader_name, loader_version = FTBPackInstaller._runtime(version)
        selected, skipped_optional, skipped_server = FTBPackInstaller._select_files(version, install_optional_files)
        download_pause_controller.raise_if_requested()
        if reporter is not None:
            reporter.status(ProgressStage.CHECKING_MODPACK, "Saving FTB modpack manifest...")
        minecraft = VersionManager.load(minecraft_version)
        resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version or ModLoaderManager.AUTO)
        instance = InstanceManager.create(name=name, version=minecraft, mod_loader=resolved_loader)
        try:
            if settings_override is not None:
                SettingsManager.save_dict(instance, settings_override)
            FTBPackRegistry.save(instance, {
                "projectId": int(project.project_id),
                "versionId": int(version.version_id),
                "name": project.name,
                "versionName": version.name,
                "minecraftVersion": minecraft_version,
                "loader": resolved_loader[0],
                "loaderVersion": resolved_loader[1],
                "installOptionalFiles": bool(install_optional_files),
                "minimumMemoryMb": version.minimum_memory_mb,
                "recommendedMemoryMb": version.recommended_memory_mb,
                "managedFiles": [FTBPackInstaller._registry_entry(file) for file in selected],
            })
            ModProvenanceRegistry.synchronize(instance)
            if InstanceArtworkManager.apply_provider_artwork(instance, "ftb", project.project_id, project.icon_url, reporter):
                instance = InstanceManager.load(instance.name)
        except Exception:
            InstanceManager.delete_instance(name)
            raise
        if reporter is not None:
            reporter.succeeded(ProgressStage.FINISHED, f"FTB modpack '{project.name}' manifest is ready. Mods will download on first launch.")
        return FTBModpackInstallResult(
            instance=instance,
            pack_name=project.name,
            pack_version=version.name,
            managed_files=len(selected),
            skipped_optional_files=skipped_optional,
            skipped_server_files=skipped_server,
        )

    @staticmethod
    def _runtime(version: FTBVersion) -> tuple[str, str, str]:
        minecraft_version = str(version.minecraft_version).strip()
        loader_name = FTBClient.normalize_loader(version.loader)
        loader_version = str(version.loader_version).strip()
        if not minecraft_version:
            raise RuntimeError("The FTB modpack does not declare a Minecraft version.")
        if loader_name not in FTBPackInstaller.SUPPORTED_LOADERS:
            label = version.loader or "unknown"
            raise RuntimeError(f"The FTB modpack uses an unsupported mod loader: {label}.")
        return minecraft_version, loader_name, loader_version

    @staticmethod
    def _select_files(version: FTBVersion, install_optional_files: bool) -> tuple[tuple[FTBFile, ...], int, int]:
        if len(version.files) > FTBPackInstaller.MAX_FILES:
            raise RuntimeError("The FTB modpack contains too many files to install safely.")
        selected: list[FTBFile] = []
        skipped_optional = 0
        skipped_server = 0
        total_size = 0
        seen_paths: set[str] = set()
        for file in version.files:
            if file.server_only:
                skipped_server += 1
                continue
            if file.optional and not install_optional_files:
                skipped_optional += 1
                continue
            relative = FTBPackInstaller._file_relative_path(file)
            key = relative.as_posix().casefold()
            if key in seen_paths:
                raise RuntimeError(f"The FTB modpack declares the same destination more than once: {relative.as_posix()}")
            seen_paths.add(key)
            if not file.urls:
                raise RuntimeError(f"FTB did not provide a download link or mirror for '{file.name}'.")
            if not file.sha1:
                raise RuntimeError(f"FTB did not provide a SHA-1 checksum for '{file.name}'.")
            total_size += max(0, file.size)
            if total_size > FTBPackInstaller.MAX_TOTAL_BYTES:
                raise RuntimeError("The FTB modpack is larger than the configured installation safety limit.")
            selected.append(file)
        return tuple(selected), skipped_optional, skipped_server

    @staticmethod
    def _file_relative_path(file: FTBFile) -> PurePosixPath:
        directory = str(file.path or "").replace("\\", "/").strip().strip("/")
        raw_name = str(file.name or "").replace("\\", "/").strip()
        filename_path = PurePosixPath(raw_name)
        if not raw_name or filename_path.name != raw_name or any(part in {"", ".", ".."} for part in filename_path.parts):
            raise RuntimeError(f"Unsafe path in FTB modpack file name: {file.name!r}")
        filename = filename_path.name
        raw = f"{directory}/{filename}" if directory else filename
        path = PurePosixPath(raw)
        if len(raw) > FTBPackInstaller.MAX_PATH_LENGTH or not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in FTB modpack: {raw!r}")
        if ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe Windows path in FTB modpack: {raw!r}")
        if path.parts[0].casefold() in FTBPackInstaller.RESERVED_ROOT_NAMES:
            raise RuntimeError(f"Reserved path in FTB modpack: {raw!r}")
        return path

    @staticmethod
    def _registry_entry(file: FTBFile) -> dict[str, object]:
        return {
            "fileId": file.file_id,
            "fileName": file.name,
            "path": FTBPackInstaller._file_relative_path(file).as_posix(),
            "sha1": file.sha1,
            "size": file.size,
            "urls": list(file.urls),
            "optional": file.optional,
            "clientOnly": file.client_only,
            "fileType": file.file_type,
            "pendingDownload": True,
            "lastDownloadError": "",
            "provider": "ftb",
        }

    @staticmethod
    def _validated_instance_name(value: str) -> str:
        name = str(value).strip()
        if not name or name in {".", ".."} or name.endswith((".", " ")) or not FTBPackInstaller.INSTANCE_NAME_PATTERN.fullmatch(name):
            raise RuntimeError("The modpack instance name contains invalid Windows filename characters or is longer than 80 characters.")
        return name
