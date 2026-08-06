from __future__ import annotations

from pathlib import PurePosixPath
import re

from src.core.atlauncher.atlauncher_client import ATLauncherClient
from src.core.atlauncher.atlauncher_pack_registry import ATLauncherPackRegistry
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.network.download_pause import download_pause_controller
from src.core.progress.progress_reporter import ProgressReporter
from src.models.atlauncher.install_result import ATLauncherModpackInstallResult
from src.models.atlauncher.version import ATLauncherFile, ATLauncherVersion
from src.models.progress.progress_stage import ProgressStage


class ATLauncherPackInstaller:
    MAX_FILES = 20_000
    MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024
    MAX_PATH_LENGTH = 240
    RESERVED_ROOT_NAMES = {"instance.json", "settings.json", ".mcw"}
    INSTANCE_NAME_PATTERN = re.compile(r'^[^<>:"/\\|?*\x00-\x1F]{1,80}$')
    SUPPORTED_LOADERS = frozenset({ModLoaderManager.VANILLA, *ModLoaderManager.MODDED_LOADERS})

    @staticmethod
    def install(safe_name: str, version_name: str, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> ATLauncherModpackInstallResult:
        name = ATLauncherPackInstaller._validated_instance_name(instance_name)
        if InstanceManager.is_instance_exist(name):
            raise RuntimeError(f"Instance '{name}' already exists.")
        allowed = ATLauncherClient._normalized_release_types(allowed_release_types)
        project = ATLauncherClient.get_project(safe_name)
        version = ATLauncherClient.get_version(safe_name, version_name)
        if version.release_type not in allowed:
            raise RuntimeError(f"ATLauncher pack version '{version.version}' uses the disabled {version.release_type} channel.")
        minecraft_version, loader_name, loader_version = ATLauncherPackInstaller._runtime(version)
        selected, skipped_optional, skipped_server, manual = ATLauncherPackInstaller._select_files(version, install_optional_files)
        if manual:
            names = ", ".join(file.name for file in manual[:8])
            raise RuntimeError(f"This ATLauncher pack requires browser-assisted files that MCW Launcher cannot download automatically yet: {names}")
        if version.unsupported_actions:
            details = ", ".join(version.unsupported_actions[:8])
            raise RuntimeError(f"This ATLauncher pack uses installation actions not supported in this beta: {details}")
        download_pause_controller.raise_if_requested()
        if reporter is not None:
            reporter.status(ProgressStage.CHECKING_MODPACK, "Saving ATLauncher modpack manifest...")
        minecraft = VersionManager.load(minecraft_version)
        resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
        instance = InstanceManager.create(name=name, version=minecraft, mod_loader=resolved_loader)
        try:
            effective_settings = settings_override
            if effective_settings is None and version.recommended_memory_mb > 0:
                effective_settings = InstanceManager.default_instance_settings()
                java = effective_settings.setdefault("java", {})
                java["max_memory"] = max(int(java.get("max_memory", 0) or 0), version.recommended_memory_mb)
            if effective_settings is not None:
                SettingsManager.save_dict(instance, effective_settings)
            config_bundle = None
            if version.config_bundle is not None:
                config_bundle = {
                    "url": version.config_bundle.url,
                    "sha1": version.config_bundle.sha1,
                    "size": version.config_bundle.size,
                    "applied": False,
                    "pendingDownload": True,
                    "lastDownloadError": "",
                }
            ATLauncherPackRegistry.save(instance, {
                "packId": project.pack_id,
                "safeName": project.safe_name,
                "name": project.name,
                "versionId": version.version_id,
                "versionName": version.version,
                "minecraftVersion": minecraft_version,
                "loader": resolved_loader[0],
                "loaderVersion": resolved_loader[1],
                "installOptionalFiles": bool(install_optional_files),
                "minimumMemoryMb": version.minimum_memory_mb,
                "recommendedMemoryMb": version.recommended_memory_mb,
                "managedFiles": [ATLauncherPackInstaller._registry_entry(file) for file in selected],
                "configBundle": config_bundle,
                "unsupportedActions": list(version.unsupported_actions),
            })
            ModProvenanceRegistry.synchronize(instance)
            if InstanceArtworkManager.apply_provider_artwork(instance, "atlauncher", project.safe_name, project.icon_url, reporter):
                instance = InstanceManager.load(instance.name)
        except Exception:
            InstanceManager.delete_instance(name)
            raise
        if reporter is not None:
            reporter.succeeded(ProgressStage.FINISHED, f"ATLauncher pack '{project.name}' is ready. Files will download on first launch.")
        return ATLauncherModpackInstallResult(
            instance=instance,
            pack_name=project.name,
            pack_version=version.version,
            managed_files=len(selected),
            skipped_optional_files=skipped_optional,
            skipped_server_files=skipped_server,
            manual_files=0,
        )

    @staticmethod
    def _runtime(version: ATLauncherVersion) -> tuple[str, str, str]:
        minecraft_version = str(version.minecraft_version).strip()
        loader_name = ATLauncherClient.normalize_loader(version.loader)
        loader_version = str(version.loader_version).strip()
        if not minecraft_version:
            raise RuntimeError("The ATLauncher pack does not declare a Minecraft version.")
        if loader_name not in ATLauncherPackInstaller.SUPPORTED_LOADERS:
            raise RuntimeError(f"The ATLauncher pack uses an unsupported mod loader: {version.loader or 'unknown'}.")
        if loader_name == ModLoaderManager.VANILLA:
            loader_version = "-1"
        return minecraft_version, loader_name, loader_version or ModLoaderManager.AUTO

    @staticmethod
    def _select_files(version: ATLauncherVersion, install_optional_files: bool) -> tuple[tuple[ATLauncherFile, ...], int, int, tuple[ATLauncherFile, ...]]:
        if len(version.files) > ATLauncherPackInstaller.MAX_FILES:
            raise RuntimeError("The ATLauncher pack contains too many files to install safely.")
        by_name = {file.name.casefold(): file for file in version.files if file.name}
        selected: list[ATLauncherFile] = []
        selected_keys: set[str] = set()
        skipped_optional = 0
        skipped_server = 0
        manual: list[ATLauncherFile] = []
        total_size = 0
        seen_paths: set[str] = set()

        def add(file: ATLauncherFile) -> None:
            nonlocal total_size
            identity = file.file_id or file.path.casefold()
            if identity in selected_keys:
                return
            if file.server_only:
                return
            relative = ATLauncherPackInstaller._file_relative_path(file)
            path_key = relative.as_posix().casefold()
            if path_key in seen_paths:
                raise RuntimeError(f"The ATLauncher pack declares the same destination more than once: {relative.as_posix()}")
            seen_paths.add(path_key)
            if file.download_type == "browser":
                manual.append(file)
            elif not file.urls:
                raise RuntimeError(f"ATLauncher did not provide a download link for '{file.name}'.")
            if not file.sha1 and not file.md5:
                raise RuntimeError(f"ATLauncher did not provide a checksum for '{file.name}'.")
            total_size += max(0, file.size)
            if total_size > ATLauncherPackInstaller.MAX_TOTAL_BYTES:
                raise RuntimeError("The ATLauncher pack is larger than the configured installation safety limit.")
            selected_keys.add(identity)
            selected.append(file)
            for dependency in file.dependencies:
                dependency_file = by_name.get(dependency.casefold())
                if dependency_file is not None:
                    add(dependency_file)

        for file in version.files:
            if file.server_only:
                skipped_server += 1
                continue
            if file.optional and not install_optional_files:
                skipped_optional += 1
                continue
            if file.optional and install_optional_files and not (file.selected or file.recommended):
                skipped_optional += 1
                continue
            add(file)
        return tuple(selected), skipped_optional, skipped_server, tuple(manual)

    @staticmethod
    def _file_relative_path(file: ATLauncherFile) -> PurePosixPath:
        raw = str(file.path or file.name or "").replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(raw)
        if len(raw) > ATLauncherPackInstaller.MAX_PATH_LENGTH or not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in ATLauncher pack: {raw!r}")
        if ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe Windows path in ATLauncher pack: {raw!r}")
        if path.parts[0].casefold() in ATLauncherPackInstaller.RESERVED_ROOT_NAMES and path.parts[0].casefold() != ".mcw":
            raise RuntimeError(f"Reserved path in ATLauncher pack: {raw!r}")
        return path

    @staticmethod
    def _registry_entry(file: ATLauncherFile) -> dict[str, object]:
        return {
            "fileId": file.file_id,
            "name": file.name,
            "fileName": PurePosixPath(file.path).name,
            "path": ATLauncherPackInstaller._file_relative_path(file).as_posix(),
            "sha1": file.sha1,
            "md5": file.md5,
            "size": file.size,
            "urls": list(file.urls),
            "optional": file.optional,
            "clientOnly": file.client_only,
            "library": file.library,
            "pendingDownload": True,
            "lastDownloadError": "",
            "provider": "atlauncher",
        }

    @staticmethod
    def _validated_instance_name(value: str) -> str:
        name = str(value).strip()
        if not name or name in {".", ".."} or name.endswith((".", " ")) or not ATLauncherPackInstaller.INSTANCE_NAME_PATTERN.fullmatch(name):
            raise RuntimeError("The modpack instance name contains invalid Windows filename characters or is longer than 80 characters.")
        return name
