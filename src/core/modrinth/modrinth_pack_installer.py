from __future__ import annotations

from pathlib import Path, PurePosixPath
from uuid import uuid4
from types import SimpleNamespace
import hashlib
import json
import re
import shutil
import stat
import zipfile

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_errors import ModrinthModpackManualDownloadRequired
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.network.artifact_download_service import ArtifactDownloadError, artifact_download_service
from src.core.network.download_pause import download_pause_controller
from src.core.progress.progress_reporter import ProgressReporter
from src.core.package.provider_package_store import ProviderPackageStore
from src.models.modrinth.install_result import ModrinthModpackInstallResult
from src.models.modrinth.manual_download import ModrinthManualDownload
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class ModrinthPackInstaller:
    INDEX_NAME = "modrinth.index.json"
    FORMAT_VERSION = 1
    MAX_WORKERS = 8
    MAX_INDEX_BYTES = 8 * 1024 * 1024
    MAX_FILES = 20_000
    MAX_TOTAL_DOWNLOAD_BYTES = 50 * 1024 * 1024 * 1024
    MAX_OVERRIDE_BYTES = 2 * 1024 * 1024 * 1024
    MAX_PATH_LENGTH = 240
    RESERVED_ROOT_NAMES = {"instance.json", "settings.json", ".mcw"}
    INSTANCE_NAME_PATTERN = re.compile(r'^[^<>:"/\\|?*\x00-\x1F]{1,80}$')

    @staticmethod
    def install(project_id: str, version_id: str, instance_name: str, install_optional_files: bool = True, allowed_version_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = "", settings_override: dict | None = None) -> ModrinthModpackInstallResult:
        project = ModrinthClient.get_project(project_id)
        requested_name = str(instance_name or "").strip()
        base_name = ModrinthPackInstaller._validated_instance_name(requested_name or project.title)
        normalized_name = base_name if requested_name else InstanceManager.next_available_name(base_name)
        if requested_name and InstanceManager.is_instance_exist(normalized_name):
            raise RuntimeError(f"Instance '{normalized_name}' already exists.")
        if project.project_type != "modpack":
            raise RuntimeError(f"'{project.title}' is not a Modrinth modpack.")
        version = ModrinthClient.get_version(version_id)
        if version.project_id != project.project_id:
            raise RuntimeError("The selected Modrinth version does not belong to this modpack.")
        allowed_types = ModrinthClient.normalize_version_types(allowed_version_types)
        if version.version_type not in allowed_types:
            raise RuntimeError(f"Modrinth modpack version '{version.version_number}' uses the disabled {version.version_type} channel.")
        pack_file = version.primary_file(".mrpack")
        pack_path = Paths.modrinth_pack_cache(project.project_id, version.version_id, pack_file.filename)
        project_url = f"https://modrinth.com/modpack/{project.slug or project.project_id}"
        version_url = f"{project_url}/version/{version.version_id}"
        try:
            ModrinthDownloader.download_file(
                pack_file,
                pack_path,
                reporter=reporter,
                progress_stage=ProgressStage.DOWNLOADING_MODPACK,
                progress_message=f"Downloading {project.title} manifest...",
                purpose="modpack-archive",
                page_url=version_url,
                project_url=project_url,
                project_id=project.project_id,
                version_id=version.version_id,
            )
        except ArtifactDownloadError as error:
            requirement = ModrinthManualDownload(
                project_id=project.project_id,
                version_id=version.version_id,
                project_name=project.title,
                file_name=pack_file.filename,
                file_size=pack_file.size,
                sha1=pack_file.sha1,
                sha512=pack_file.sha512,
                project_url=error.failure.project_url or project_url,
                version_url=error.failure.page_url or version_url,
                direct_url=error.failure.url or pack_file.url,
                reason=f"Automatic download failed ({error.failure.reason.value}): {error.failure.detail}",
                failure_reason=error.failure.reason.value,
                http_status=error.failure.http_status,
                attempts=error.failure.attempts,
                retryable=error.failure.retryable,
                managed_kind="modpack_archive",
            )
            raise ModrinthModpackManualDownloadRequired(requirement, project.project_id, version.version_id, normalized_name, install_optional_files, allowed_types, expected_loader, settings_override) from error
        return ModrinthPackInstaller._install_archive(project, version, pack_path, normalized_name, install_optional_files, reporter, expected_loader, settings_override)

    @staticmethod
    def install_local_archive(pack_path: Path, instance_name: str = "", install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> ModrinthModpackInstallResult:
        source = Path(pack_path)
        if not source.is_file():
            raise RuntimeError("The selected Modrinth package does not exist.")
        details = ModrinthPackInstaller.inspect(source)
        requested_name = str(instance_name or details.get("name") or source.stem).strip()
        normalized_name = ModrinthPackInstaller._validated_instance_name(requested_name)
        if InstanceManager.is_instance_exist(normalized_name):
            normalized_name = InstanceManager.next_available_name(normalized_name)
        with zipfile.ZipFile(source, "r") as archive:
            index = ModrinthPackInstaller._read_index(archive)
        version_label = str(index.get("versionId") or index.get("name") or source.stem).strip()
        provider_project, provider_version = ModrinthPackInstaller._resolve_local_provider_metadata(version_label)
        project = provider_project or SimpleNamespace(project_id="", title=str(index.get("name") or source.stem), icon_url="")
        version = provider_version or SimpleNamespace(version_id=version_label, version_number=version_label)
        result = ModrinthPackInstaller._install_archive(project, version, source, normalized_name, install_optional_files, reporter, "", settings_override, apply_provider_artwork=False)
        try:
            ProviderPackageStore.store_native_package(
                result.instance,
                source,
                provider="modrinth",
                package_format="mrpack",
                origin={
                    "projectId": str(getattr(project, "project_id", "") or ""),
                    "versionId": str(getattr(version, "version_id", version_label) or version_label),
                    "packName": str(getattr(project, "title", "") or index.get("name") or source.stem),
                    "packVersion": str(getattr(version, "version_number", version_label) or version_label),
                    "source": "local_import",
                },
            )
        except Exception:
            InstanceManager.delete_instance(result.instance.name)
            raise
        result = ModrinthPackInstaller._apply_local_archive_artwork(result, source, project, reporter)
        return result

    @staticmethod
    def _resolve_local_provider_metadata(version_id: str) -> tuple[object | None, object | None]:
        """Resolve a local mrpack only when its version ID maps unambiguously."""
        candidate = str(version_id or "").strip()
        if not candidate:
            return None, None
        try:
            version = ModrinthClient.get_version(candidate)
            project = ModrinthClient.get_project(version.project_id)
        except Exception:
            return None, None
        if str(getattr(project, "project_type", "")).casefold() != "modpack":
            return None, None
        return project, version

    @staticmethod
    def _apply_local_archive_artwork(result: ModrinthModpackInstallResult, source: Path, project: object, reporter: ProgressReporter | None) -> ModrinthModpackInstallResult:
        instance = result.instance
        try:
            with zipfile.ZipFile(source, "r") as archive:
                embedded = InstanceArtworkManager.apply_embedded_archive_artwork(instance, archive)
            if not embedded and not InstanceArtworkManager.has_custom_artwork(InstanceManager.load(instance.name)):
                InstanceArtworkManager.apply_provider_artwork(instance, "modrinth", getattr(project, "project_id", ""), getattr(project, "icon_url", ""), reporter)
            refreshed = InstanceManager.load(instance.name)
            return ModrinthModpackInstallResult(instance=refreshed, pack_name=result.pack_name, pack_version=result.pack_version, installed_files=result.installed_files, skipped_optional_files=result.skipped_optional_files, skipped_server_files=result.skipped_server_files)
        except Exception:
            return result

    @staticmethod
    def install_manual_archive(request: ModrinthModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> ModrinthModpackInstallResult:
        project = ModrinthClient.get_project(request.project_id)
        version = ModrinthClient.get_version(request.version_id)
        requirement = request.requirement
        pack_path = Paths.modrinth_pack_cache(project.project_id, version.version_id, requirement.file_name)
        artifact_request = ArtifactRequest(
            provider="modrinth",
            purpose="manual-modpack-archive",
            destination=pack_path,
            urls=(requirement.direct_url,) if requirement.direct_url else (),
            page_url=requirement.version_url,
            project_url=requirement.project_url,
            expected_filename=requirement.file_name,
            expected_size=requirement.file_size,
            hashes={key: value for key, value in {"sha1": requirement.sha1, "sha512": requirement.sha512}.items() if value},
            project_id=requirement.project_id,
            version_id=requirement.version_id,
        )
        artifact_download_service.accept_manual_file(artifact_request, Path(source))
        return ModrinthPackInstaller._install_archive(project, version, pack_path, request.instance_name, request.install_optional_files, reporter, request.expected_loader, request.settings_override)

    @staticmethod
    def _install_archive(project, version, pack_path: Path, normalized_name: str, install_optional_files: bool, reporter: ProgressReporter | None, expected_loader: str, settings_override: dict | None = None, apply_provider_artwork: bool = True) -> ModrinthModpackInstallResult:
        staging = Paths.modrinth_staging_root() / uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        created_instance = None
        try:
            download_pause_controller.raise_if_requested()
            with zipfile.ZipFile(pack_path, "r") as archive:
                index = ModrinthPackInstaller._read_index(archive)
                minecraft_version, loader_name, loader_version = ModrinthPackInstaller._parse_dependencies(index)
                selected_files, skipped_optional, skipped_server = ModrinthPackInstaller._selected_files(index, install_optional_files)
                managed_files = {entry["path"].casefold(): entry for entry in ModrinthPackInstaller._managed_download_entries(selected_files)}
                for entry in ModrinthPackInstaller._extract_layer(archive, "overrides", staging):
                    managed_files[entry["path"].casefold()] = entry
                for entry in ModrinthPackInstaller._extract_layer(archive, "client-overrides", staging):
                    managed_files[entry["path"].casefold()] = entry
            download_pause_controller.raise_if_requested()
            selected_loader = str(expected_loader or "").strip().lower()
            if selected_loader and selected_loader != loader_name:
                raise RuntimeError(f"This modpack uses {loader_name.title()}, but the browser filter is set to {selected_loader.title()}.")
            base_version = VersionManager.load(minecraft_version)
            resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
            download_pause_controller.raise_if_requested()
            created_instance = InstanceManager.create(name=normalized_name, version=base_version, mod_loader=resolved_loader)
            if settings_override is not None:
                SettingsManager.save_dict(created_instance, settings_override)
            shutil.copytree(staging, created_instance.instance_dir, dirs_exist_ok=True)
            ModrinthPackInstaller._write_metadata(created_instance.instance_dir, project.project_id, version.version_id, project.title, version.version_number, minecraft_version, loader_name, loader_version, list(managed_files.values()), install_optional_files)
            ModProvenanceRegistry.synchronize(created_instance)
            if apply_provider_artwork and InstanceArtworkManager.apply_provider_artwork(created_instance, "modrinth", project.project_id, getattr(project, "icon_url", ""), reporter):
                created_instance = InstanceManager.load(created_instance.name)
            return ModrinthModpackInstallResult(instance=created_instance, pack_name=project.title, pack_version=version.version_number, installed_files=len(selected_files), skipped_optional_files=skipped_optional, skipped_server_files=skipped_server)
        except Exception:
            if created_instance is not None:
                InstanceManager.delete_instance(created_instance.name)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def inspect(pack_path: Path) -> dict:
        with zipfile.ZipFile(pack_path, "r") as archive:
            index = ModrinthPackInstaller._read_index(archive)
            minecraft_version, loader_name, loader_version = ModrinthPackInstaller._parse_dependencies(index)
        return {"name": str(index.get("name") or ""), "summary": str(index.get("summary") or ""), "minecraft": minecraft_version, "loader": loader_name, "loader_version": loader_version, "fabric_loader": loader_version if loader_name == ModLoaderManager.FABRIC else "", "quilt_loader": loader_version if loader_name == ModLoaderManager.QUILT else "", "forge": loader_version if loader_name == ModLoaderManager.FORGE else "", "neoforge": loader_version if loader_name == ModLoaderManager.NEOFORGE else "", "files": len(index.get("files", []))}

    @staticmethod
    def _read_index(archive: zipfile.ZipFile) -> dict:
        try:
            raw = archive.read(ModrinthPackInstaller.INDEX_NAME)
        except KeyError as error:
            raise RuntimeError("The .mrpack file is missing modrinth.index.json.") from error
        if len(raw) > ModrinthPackInstaller.MAX_INDEX_BYTES:
            raise RuntimeError("modrinth.index.json is too large to process safely.")
        try:
            index = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid modrinth.index.json: {error}") from error
        if not isinstance(index, dict):
            raise RuntimeError("modrinth.index.json must contain an object.")
        if int(index.get("formatVersion", 0) or 0) != ModrinthPackInstaller.FORMAT_VERSION:
            raise RuntimeError(f"Unsupported Modrinth pack format version: {index.get('formatVersion')}")
        if str(index.get("game") or "").strip().lower() != "minecraft":
            raise RuntimeError("This Modrinth pack is not for Minecraft.")
        if not isinstance(index.get("files"), list) or not isinstance(index.get("dependencies"), dict):
            raise RuntimeError("The Modrinth pack index is incomplete.")
        return index

    @staticmethod
    def _parse_dependencies(index: dict) -> tuple[str, str, str]:
        dependencies = index.get("dependencies", {})
        minecraft_version = str(dependencies.get("minecraft") or "").strip()
        fabric_loader = str(dependencies.get("fabric-loader") or "").strip()
        quilt_loader = str(dependencies.get("quilt-loader") or "").strip()
        forge_loader = str(dependencies.get("forge") or "").strip()
        neoforge_loader = str(dependencies.get("neoforge") or "").strip()
        if not minecraft_version:
            raise RuntimeError("The modpack does not declare a Minecraft version.")
        declared = [(ModLoaderManager.FABRIC, fabric_loader), (ModLoaderManager.QUILT, quilt_loader), (ModLoaderManager.FORGE, forge_loader), (ModLoaderManager.NEOFORGE, neoforge_loader)]
        selected = [(name, version) for name, version in declared if version]
        if not selected:
            raise RuntimeError("The modpack does not declare a supported Fabric, Quilt, Forge, or NeoForge loader.")
        if len(selected) != 1:
            raise RuntimeError("The modpack declares more than one supported loader and cannot be installed safely.")
        loader_name, loader_version = selected[0]
        return minecraft_version, loader_name, loader_version

    @staticmethod
    def _selected_files(index: dict, install_optional_files: bool) -> tuple[list[dict], int, int]:
        selected: list[dict] = []
        skipped_optional = 0
        skipped_server = 0
        files = index.get("files", [])
        if len(files) > ModrinthPackInstaller.MAX_FILES:
            raise RuntimeError("The modpack contains too many files to install safely.")
        total_size = 0
        for item in files:
            if not isinstance(item, dict):
                raise RuntimeError("The modpack contains an invalid file entry.")
            client_state = str((item.get("env") or {}).get("client") or "required").strip().lower() if isinstance(item.get("env"), dict) else "required"
            if client_state == "unsupported":
                skipped_server += 1
                continue
            if client_state == "optional" and not install_optional_files:
                skipped_optional += 1
                continue
            ModrinthPackInstaller._safe_relative_path(str(item.get("path") or ""))
            hashes = item.get("hashes", {}) if isinstance(item.get("hashes"), dict) else {}
            if not str(hashes.get("sha1") or "") or not str(hashes.get("sha512") or ""):
                raise RuntimeError(f"Modpack file '{item.get('path')}' is missing required hashes.")
            downloads = item.get("downloads", [])
            if not isinstance(downloads, list):
                raise RuntimeError(f"Modpack file '{item.get('path')}' has an invalid download URL list.")
            file_size = int(item.get("fileSize", 0) or 0)
            if file_size < 0:
                raise RuntimeError(f"Modpack file '{item.get('path')}' has an invalid size.")
            total_size += file_size
            if total_size > ModrinthPackInstaller.MAX_TOTAL_DOWNLOAD_BYTES:
                raise RuntimeError("The modpack download is larger than the configured safety limit.")
            selected.append(item)
        return selected, skipped_optional, skipped_server

    @staticmethod
    def _download_files(files: list[dict], staging: Path, reporter: ProgressReporter | None = None) -> None:
        total = len(files)
        if reporter is not None:
            reporter.files(stage=ProgressStage.DOWNLOADING_MODPACK, message="Downloading modpack files...", current=0, total=total)
        for completed, item in enumerate(files, start=1):
            download_pause_controller.raise_if_requested()
            relative = ModrinthPackInstaller._safe_relative_path(str(item.get("path") or ""))
            hashes = item.get("hashes", {})
            ModrinthDownloader.download_urls(
                urls=tuple(str(url) for url in item.get("downloads", [])),
                destination=staging.joinpath(*relative.parts),
                sha1=str(hashes.get("sha1") or ""),
                sha512=str(hashes.get("sha512") or ""),
                expected_size=int(item.get("fileSize", 0) or 0),
                restrict_hosts=True,
                purpose="modpack-artifact",
                reporter=reporter,
                progress_stage=ProgressStage.DOWNLOADING_MODPACK,
                progress_message=f"Downloading {relative.name}...",
            )
            if reporter is not None:
                reporter.files(stage=ProgressStage.DOWNLOADING_MODPACK, message="Downloading modpack files...", current=completed, total=total)

    @staticmethod
    def _managed_download_entries(files: list[dict]) -> list[dict]:
        managed: list[dict] = []
        for item in files:
            relative = ModrinthPackInstaller._safe_relative_path(str(item.get("path") or ""))
            hashes = item.get("hashes", {}) if isinstance(item.get("hashes"), dict) else {}
            client_state = str((item.get("env") or {}).get("client") or "required").strip().lower() if isinstance(item.get("env"), dict) else "required"
            managed.append({"path": relative.as_posix(), "fileName": relative.name, "sha1": str(hashes.get("sha1") or "").lower(), "sha512": str(hashes.get("sha512") or "").lower(), "size": int(item.get("fileSize", 0) or 0), "source": "download", "provider": "modrinth", "downloads": [str(url).strip() for url in item.get("downloads", []) if str(url).strip()], "required": client_state == "required"})
        return managed

    @staticmethod
    def _extract_layer(archive: zipfile.ZipFile, prefix: str, staging: Path) -> list[dict]:
        normalized_prefix = prefix.rstrip("/") + "/"
        extracted_size = 0
        managed: list[dict] = []
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name.startswith(normalized_prefix) or name.endswith("/"):
                continue
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise RuntimeError(f"Symbolic links are not allowed in modpack overrides: {name}")
            extracted_size += int(info.file_size or 0)
            if extracted_size > ModrinthPackInstaller.MAX_OVERRIDE_BYTES:
                raise RuntimeError(f"The {prefix} layer is larger than the configured safety limit.")
            relative = ModrinthPackInstaller._safe_relative_path(name[len(normalized_prefix):])
            target = staging.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            sha1 = hashlib.sha1(usedforsecurity=False)
            sha512 = hashlib.sha512()
            written = 0
            with archive.open(info, "r") as source, target.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    sha1.update(chunk)
                    sha512.update(chunk)
                    written += len(chunk)
            managed.append({"path": relative.as_posix(), "fileName": relative.name, "sha1": sha1.hexdigest(), "sha512": sha512.hexdigest(), "size": written, "source": prefix, "provider": "pack"})
        return managed

    @staticmethod
    def _safe_relative_path(value: str) -> PurePosixPath:
        normalized = str(value).replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if len(normalized) > ModrinthPackInstaller.MAX_PATH_LENGTH:
            raise RuntimeError(f"Path is too long for a Windows instance: {value!r}")
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in Modrinth pack: {value!r}")
        first = path.parts[0].casefold()
        if first in ModrinthPackInstaller.RESERVED_ROOT_NAMES or ":" in first:
            raise RuntimeError(f"Reserved path in Modrinth pack: {value!r}")
        return path

    @staticmethod
    def _validated_instance_name(value: str) -> str:
        name = str(value).strip()
        if not name or name in {".", ".."} or name.endswith((".", " ")) or not ModrinthPackInstaller.INSTANCE_NAME_PATTERN.fullmatch(name):
            raise RuntimeError("The modpack instance name contains invalid Windows filename characters or is longer than 80 characters.")
        return name

    @staticmethod
    def _write_metadata(instance_dir: Path, project_id: str, version_id: str, title: str, version_number: str, minecraft_version: str, loader_name: str, loader_version: str, managed_files: list[dict], install_optional_files: bool) -> None:
        verification_cache = ModrinthPackRegistry.build_verification_cache(instance_dir, managed_files)
        ModrinthPackRegistry.save(instance_dir, {"projectId": project_id, "versionId": version_id, "name": title, "versionNumber": version_number, "minecraftVersion": minecraft_version, "loader": loader_name, "loaderVersion": loader_version, "installOptionalFiles": bool(install_optional_files), "managedFiles": managed_files, "preservedFiles": [], "verificationCache": verification_cache})
