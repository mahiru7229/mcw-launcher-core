from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import shutil
import stat
import zipfile

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
from src.core.curseforge.curseforge_links import file_page_url
from src.core.curseforge.curseforge_errors import CurseForgeModpackManualDownloadRequired
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.progress.progress_reporter import ProgressReporter
from src.core.package.provider_package_store import ProviderPackageStore
from src.models.curseforge.install_result import CurseForgeModpackInstallResult
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.progress.progress_stage import ProgressStage


class CurseForgePackInstaller:
    MANIFEST_NAME = "manifest.json"
    MAX_MANIFEST_BYTES = 4 * 1024 * 1024
    MAX_FILES = 5000
    MAX_OVERRIDE_BYTES = 2 * 1024 * 1024 * 1024
    MAX_PATH_LENGTH = 240
    MAX_WORKERS = 8
    RESERVED_ROOT_NAMES = {"instance.json", "settings.json", ".mcw"}
    INSTANCE_NAME_PATTERN = re.compile(r'^[^<>:"/\\|?*\x00-\x1F]{1,80}$')
    SUPPORTED_LOADERS = (ModLoaderManager.FABRIC, ModLoaderManager.QUILT, ModLoaderManager.FORGE, ModLoaderManager.NEOFORGE)

    @staticmethod
    def install(project_id: int, file_id: int, instance_name: str, install_optional_files: bool = True, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None = None, reporter: ProgressReporter | None = None, expected_loader: str = "", settings_override: dict | None = None) -> CurseForgeModpackInstallResult:
        name, allowed, project, file = CurseForgePackInstaller._prepare_install(project_id, file_id, instance_name, allowed_release_types)
        pack_path = Paths.curseforge_pack_cache(project_id, file_id, file.file_name)
        try:
            CurseForgeDownloader.download_file(file, pack_path, reporter=reporter, stage=ProgressStage.DOWNLOADING_MODPACK, message=f"Downloading {project.name} manifest...", project_name=project.name, project_url=project.project_url)
        except CurseForgeManualDownloadRequired as error:
            page_url = file_page_url(project.project_url or error.requirement.project_url, file_id) or error.requirement.version_url
            requirement = replace(
                error.requirement,
                project_name=project.name,
                project_url=page_url or project.project_url or error.requirement.project_url,
                version_url=page_url,
                managed_kind="modpack_archive",
            )
            raise CurseForgeModpackManualDownloadRequired(requirement, project_id, file_id, name, install_optional_files, allowed, expected_loader, settings_override) from error
        return CurseForgePackInstaller._install_from_archive(project_id, file_id, name, install_optional_files, project, file, pack_path, reporter, expected_loader, settings_override)

    @staticmethod
    def install_local_archive(pack_path: Path, instance_name: str = "", install_optional_files: bool = True, reporter: ProgressReporter | None = None, settings_override: dict | None = None) -> CurseForgeModpackInstallResult:
        source = Path(pack_path)
        if not source.is_file():
            raise RuntimeError("The selected CurseForge package does not exist.")
        try:
            archive = zipfile.ZipFile(source, "r")
        except (OSError, zipfile.BadZipFile) as error:
            raise RuntimeError("The selected CurseForge modpack archive is not a valid ZIP file.") from error
        with archive:
            manifest = CurseForgePackInstaller._read_manifest(archive)
            minecraft_version, loader_name, loader_version = CurseForgePackInstaller._parse_loader(manifest)
            pack_name = str(manifest.get("name") or source.stem).strip() or source.stem
            version_name = str(manifest.get("version") or manifest.get("versionName") or "Imported").strip() or "Imported"
            provider_project_id = CurseForgePackInstaller._manifest_project_id(manifest)
            requested = str(instance_name or pack_name).strip()
            name = CurseForgePackInstaller._validated_instance_name(requested)
            if InstanceManager.is_instance_exist(name):
                name = InstanceManager.next_available_name(name)
            entries, skipped = CurseForgePackInstaller._unresolved_files(manifest, install_optional_files)
            version = VersionManager.load(minecraft_version)
            resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
            instance = InstanceManager.create(name=name, version=version, mod_loader=resolved_loader)
            try:
                if settings_override is not None:
                    SettingsManager.save_dict(instance, settings_override)
                override_mods = CurseForgePackInstaller._extract_overrides(archive, str(manifest.get("overrides") or "overrides"), Path(instance.instance_dir), reporter)
                CurseForgePackRegistry.save(instance, {
                    "projectId": 0,
                    "fileId": 0,
                    "name": pack_name,
                    "versionName": version_name,
                    "minecraftVersion": minecraft_version,
                    "loader": loader_name,
                    "loaderVersion": loader_version,
                    "installOptionalFiles": bool(install_optional_files),
                    "managedFiles": entries,
                    "lastDownloadFailures": [],
                    "importedFromNativePackage": True,
                })
                ModProvenanceRegistry.synchronize(instance)
                ModProvenanceRegistry.record_many(instance, [{**entry, "provider": "curseforge", "managedByModpack": True, "packProvider": "curseforge"} for entry in override_mods])
                ProviderPackageStore.store_native_package(
                    instance,
                    source,
                    provider="curseforge",
                    package_format="curseforge_zip",
                    origin={
                        "projectId": provider_project_id,
                        "packName": pack_name,
                        "packVersion": version_name,
                        "source": "local_import",
                    },
                )
            except Exception:
                InstanceManager.delete_instance(name)
                raise
            instance = CurseForgePackInstaller._apply_local_archive_artwork(instance, archive, provider_project_id, reporter)
        return CurseForgeModpackInstallResult(instance=instance, pack_name=pack_name, pack_version=version_name, managed_files=len(entries), skipped_optional_files=skipped)

    @staticmethod
    def _manifest_project_id(manifest: dict) -> int:
        for key in ("projectID", "projectId", "project_id"):
            try:
                value = int(manifest.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0

    @staticmethod
    def _apply_local_archive_artwork(instance, archive: zipfile.ZipFile, project_id: int, reporter: ProgressReporter | None):
        try:
            embedded = InstanceArtworkManager.apply_embedded_archive_artwork(instance, archive)
            if not embedded and project_id > 0 and not InstanceArtworkManager.has_custom_artwork(InstanceManager.load(instance.name)):
                try:
                    project = CurseForgeClient.get_project(project_id)
                except Exception:
                    project = None
                if project is not None:
                    InstanceArtworkManager.apply_provider_artwork(instance, "curseforge", project_id, getattr(project, "logo_url", ""), reporter)
            return InstanceManager.load(instance.name)
        except Exception:
            return instance

    @staticmethod
    def install_manual_archive(request: CurseForgeModpackManualDownloadRequired, source: Path, reporter: ProgressReporter | None = None) -> CurseForgeModpackInstallResult:
        if not isinstance(request, CurseForgeModpackManualDownloadRequired):
            raise RuntimeError("The pending CurseForge modpack request is invalid.")
        name, _allowed, project, file = CurseForgePackInstaller._prepare_install(
            request.project_id,
            request.file_id,
            request.instance_name,
            request.allowed_release_types,
        )
        source_path = Path(source)
        CurseForgePackInstaller._verify_manual_archive(source_path, request.requirement)
        pack_path = Paths.curseforge_pack_cache(request.project_id, request.file_id, file.file_name)
        CurseForgePackInstaller._copy_archive_to_cache(source_path, pack_path)
        return CurseForgePackInstaller._install_from_archive(
            request.project_id,
            request.file_id,
            name,
            request.install_optional_files,
            project,
            file,
            pack_path,
            reporter,
            getattr(request, "expected_loader", ""),
            getattr(request, "settings_override", None),
        )

    @staticmethod
    def _prepare_install(project_id: int, file_id: int, instance_name: str, allowed_release_types: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, tuple[str, ...], object, object]:
        name = CurseForgePackInstaller._validated_instance_name(instance_name)
        if InstanceManager.is_instance_exist(name):
            raise RuntimeError(f"Instance '{name}' already exists.")
        allowed = CurseForgeClient.normalize_release_types(allowed_release_types)
        project = CurseForgeClient.get_project(project_id)
        file = CurseForgeClient.get_file(project_id, file_id)
        if file.release_type not in allowed:
            raise RuntimeError(f"CurseForge modpack file '{file.display_name}' uses the disabled {file.release_type} channel.")
        return name, allowed, project, file

    @staticmethod
    def _install_from_archive(project_id: int, file_id: int, name: str, install_optional_files: bool, project: object, file: object, pack_path: Path, reporter: ProgressReporter | None, expected_loader: str = "", settings_override: dict | None = None) -> CurseForgeModpackInstallResult:
        try:
            archive = zipfile.ZipFile(pack_path, "r")
        except (OSError, zipfile.BadZipFile) as error:
            raise RuntimeError("The selected CurseForge modpack archive is not a valid ZIP file.") from error
        with archive:
            manifest = CurseForgePackInstaller._read_manifest(archive)
            minecraft_version, loader_name, loader_version = CurseForgePackInstaller._parse_loader(manifest)
            CurseForgePackInstaller._validate_expected_loader(loader_name, expected_loader)
            entries, skipped = CurseForgePackInstaller._resolve_files(manifest, minecraft_version, install_optional_files, reporter)
            version = VersionManager.load(minecraft_version)
            resolved_loader = ModLoaderManager.resolve(minecraft_version, loader_name, loader_version)
            instance = InstanceManager.create(name=name, version=version, mod_loader=resolved_loader)
            try:
                if settings_override is not None:
                    SettingsManager.save_dict(instance, settings_override)
                override_mods = CurseForgePackInstaller._extract_overrides(archive, str(manifest.get("overrides") or "overrides"), Path(instance.instance_dir), reporter)
                CurseForgePackRegistry.save(instance, {
                    "projectId": int(project_id),
                    "fileId": int(file_id),
                    "name": project.name,
                    "versionName": file.display_name,
                    "minecraftVersion": minecraft_version,
                    "loader": loader_name,
                    "loaderVersion": loader_version,
                    "installOptionalFiles": bool(install_optional_files),
                    "managedFiles": entries,
                    "lastDownloadFailures": [],
                })
                ModProvenanceRegistry.synchronize(instance)
                ModProvenanceRegistry.record_many(instance, [{**entry, "provider": "curseforge", "managedByModpack": True, "packProvider": "curseforge", "packProjectId": str(project_id), "packVersionId": str(file_id)} for entry in override_mods])
                if InstanceArtworkManager.apply_provider_artwork(instance, "curseforge", project_id, getattr(project, "logo_url", ""), reporter):
                    instance = InstanceManager.load(instance.name)
            except Exception:
                InstanceManager.delete_instance(name)
                raise
        return CurseForgeModpackInstallResult(instance=instance, pack_name=project.name, pack_version=file.display_name, managed_files=len(entries), skipped_optional_files=skipped)

    @staticmethod
    def _verify_manual_archive(source: Path, requirement: CurseForgeManualDownload) -> None:
        if not source.is_file():
            raise RuntimeError("The selected CurseForge modpack file does not exist.")
        if source.suffix.casefold() != ".zip":
            raise RuntimeError("Select the original CurseForge modpack ZIP archive.")
        size = source.stat().st_size
        if requirement.file_size > 0 and size != requirement.file_size:
            raise RuntimeError(f"The selected modpack has the wrong size. Expected {requirement.file_size} bytes, got {size} bytes.")
        if requirement.sha1:
            digest = CurseForgePackInstaller._sha1(source)
            if digest.casefold() != requirement.sha1.casefold():
                raise RuntimeError("The selected modpack does not match the expected CurseForge SHA-1 checksum.")

    @staticmethod
    def _copy_archive_to_cache(source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source.resolve() == destination.resolve():
                return destination
        except OSError:
            pass
        temporary = destination.with_suffix(destination.suffix + ".part")
        temporary.unlink(missing_ok=True)
        shutil.copy2(source, temporary)
        temporary.replace(destination)
        return destination

    @staticmethod
    def _sha1(path: Path) -> str:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as input_file:
            while chunk := input_file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile) -> dict:
        try:
            info = archive.getinfo(CurseForgePackInstaller.MANIFEST_NAME)
        except KeyError as error:
            raise RuntimeError("The CurseForge modpack is missing manifest.json.") from error
        if info.file_size > CurseForgePackInstaller.MAX_MANIFEST_BYTES:
            raise RuntimeError("CurseForge manifest.json is too large to process safely.")
        try:
            data = json.loads(archive.read(info).decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid CurseForge manifest.json: {error}") from error
        if not isinstance(data, dict) or not isinstance(data.get("minecraft"), dict) or not isinstance(data.get("files"), list):
            raise RuntimeError("CurseForge manifest.json is incomplete.")
        if len(data["files"]) > CurseForgePackInstaller.MAX_FILES:
            raise RuntimeError("The CurseForge modpack contains too many files to install safely.")
        return data

    @staticmethod
    def _parse_loader(manifest: dict) -> tuple[str, str, str]:
        minecraft = manifest.get("minecraft", {})
        game_version = str(minecraft.get("version") or "").strip()
        loaders = minecraft.get("modLoaders") if isinstance(minecraft.get("modLoaders"), list) else []
        if not game_version:
            raise RuntimeError("The CurseForge modpack does not declare a Minecraft version.")
        declared = [
            (item, CurseForgePackInstaller._parse_loader_id(str(item.get("id") or "")))
            for item in loaders
            if isinstance(item, dict)
        ]
        primary = [(item, parsed) for item, parsed in declared if bool(item.get("primary", False))]
        if len(primary) > 1:
            raise RuntimeError("The CurseForge modpack declares more than one primary mod loader.")
        if primary:
            selected = primary[0][1]
            if selected is None:
                loader_id = str(primary[0][0].get("id") or "unknown")
                raise RuntimeError(f"The CurseForge modpack uses an unsupported loader: {loader_id}.")
        else:
            supported = [parsed for _item, parsed in declared if parsed is not None]
            families = {loader_name for loader_name, _loader_version in supported}
            if len(families) > 1:
                raise RuntimeError("The CurseForge modpack declares multiple supported mod-loader families and cannot be installed safely.")
            selected = supported[0] if supported else None
        if selected is None:
            raise RuntimeError("The CurseForge modpack does not declare a supported Fabric, Quilt, Forge, or NeoForge loader.")
        loader_name, loader_version = selected
        return game_version, loader_name, loader_version

    @staticmethod
    def _parse_loader_id(value: str) -> tuple[str, str] | None:
        loader_id = str(value).strip()
        normalized = loader_id.casefold()
        for loader_name in CurseForgePackInstaller.SUPPORTED_LOADERS:
            prefix = loader_name + "-"
            if not normalized.startswith(prefix):
                continue
            loader_version = loader_id[len(prefix):].strip()
            if not loader_version:
                raise RuntimeError(f"The CurseForge modpack declares an invalid {loader_name.title()} Loader version.")
            return loader_name, loader_version
        return None

    @staticmethod
    def _validate_expected_loader(actual_loader: str, expected_loader: str) -> None:
        expected = str(expected_loader).strip().casefold()
        if not expected:
            return
        if expected not in CurseForgePackInstaller.SUPPORTED_LOADERS:
            raise RuntimeError(f"Unsupported CurseForge modpack loader filter: {expected_loader}.")
        if actual_loader != expected:
            raise RuntimeError(
                f"This CurseForge modpack uses {actual_loader.title()}, "
                f"but the browser filter is set to {expected.title()}."
            )

    @staticmethod
    def _unresolved_files(manifest: dict, install_optional_files: bool) -> tuple[list[dict], int]:
        raw_files = manifest.get("files", [])
        selected = [item for item in raw_files if isinstance(item, dict) and (bool(item.get("required", True)) or install_optional_files)]
        skipped = len(raw_files) - len(selected)
        results: list[dict] = []
        seen: set[tuple[int, int]] = set()
        for item in selected:
            project_id = int(item.get("projectID") or item.get("projectId") or 0)
            file_id = int(item.get("fileID") or item.get("fileId") or 0)
            if project_id <= 0 or file_id <= 0:
                raise RuntimeError("The CurseForge modpack contains an invalid project or file ID.")
            key = (project_id, file_id)
            if key in seen:
                continue
            seen.add(key)
            synthetic_name = f"curseforge-{project_id}-{file_id}.jar"
            results.append({
                "projectId": project_id,
                "fileId": file_id,
                "fileName": synthetic_name,
                "path": f"mods/{synthetic_name}",
                "displayName": f"CurseForge {project_id}/{file_id}",
                "sha1": "",
                "size": 0,
                "downloadUrl": "",
                "required": bool(item.get("required", True)),
                "provider": "curseforge",
                "pendingDownload": True,
                "resolvePathFromProvider": True,
            })
        return sorted(results, key=lambda item: (item["projectId"], item["fileId"])), skipped

    @staticmethod
    def _resolve_files(manifest: dict, game_version: str, install_optional_files: bool, reporter: ProgressReporter | None) -> tuple[list[dict], int]:
        raw_files = manifest.get("files", [])
        selected = [item for item in raw_files if isinstance(item, dict) and (bool(item.get("required", True)) or install_optional_files)]
        skipped = len(raw_files) - len(selected)
        normalized: list[tuple[int, int, bool]] = []
        for item in selected:
            project_id = int(item.get("projectID") or item.get("projectId") or 0)
            file_id = int(item.get("fileID") or item.get("fileId") or 0)
            if project_id <= 0 or file_id <= 0:
                raise RuntimeError("The CurseForge modpack contains an invalid project or file ID.")
            normalized.append((project_id, file_id, bool(item.get("required", True))))
        if reporter is not None:
            reporter.files(stage=ProgressStage.CHECKING_MODPACK, message="Reading CurseForge modpack file metadata...", current=0, total=len(normalized))

        files = CurseForgeClient.get_files_batch([file_id for _project_id, file_id, _required in normalized])
        results: list[dict] = []
        for completed, (project_id, file_id, required) in enumerate(normalized, start=1):
            file = files.get(file_id)
            if file is None or file.project_id != project_id:
                file = CurseForgeClient.get_file(project_id, file_id)
            # The manifest's exact project/file pair is authoritative. Provider
            # game-version labels are retained for diagnostics but never block
            # a managed modpack file that the pack author selected.
            results.append({
                "projectId": project_id,
                "fileId": file_id,
                "fileName": file.file_name,
                "path": f"mods/{file.file_name}",
                "displayName": file.display_name,
                "sha1": file.sha1,
                "size": file.file_length,
                "downloadUrl": file.download_url,
                "declaredLoaders": list(file.loaders),
                "gameVersions": list(file.game_versions),
                "dependencies": [{"projectId": dependency.project_id, "relationType": dependency.relation_type} for dependency in file.dependencies],
                "dependencyMetadataResolved": True,
                "required": required,
                "provider": "curseforge",
            })
            if reporter is not None:
                reporter.files(stage=ProgressStage.CHECKING_MODPACK, message="Reading CurseForge modpack file metadata...", current=completed, total=len(normalized))
        return sorted(results, key=lambda item: (item["projectId"], item["fileId"])), skipped

    @staticmethod
    def _extract_overrides(archive: zipfile.ZipFile, prefix: str, destination: Path, reporter: ProgressReporter | None) -> list[dict]:
        normalized_prefix = str(prefix).replace("\\", "/").strip("/") + "/"
        entries = [info for info in archive.infolist() if info.filename.replace("\\", "/").startswith(normalized_prefix) and not info.is_dir()]
        total_bytes = sum(max(0, int(info.file_size or 0)) for info in entries)
        if total_bytes > CurseForgePackInstaller.MAX_OVERRIDE_BYTES:
            raise RuntimeError("The CurseForge override layer is larger than the configured safety limit.")
        written = 0
        override_mods: list[dict] = []
        if reporter is not None:
            reporter.bytes(stage=ProgressStage.INSTALLING_MOD_LOADER, message="Extracting CurseForge overrides...", current=0, total=total_bytes)
        for info in entries:
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise RuntimeError(f"Symbolic links are not allowed in CurseForge overrides: {info.filename}")
            name = info.filename.replace("\\", "/")[len(normalized_prefix):]
            relative = CurseForgePackInstaller._safe_relative_path(name)
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha1(usedforsecurity=False)
            file_written = 0
            with archive.open(info, "r") as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    file_written += len(chunk)
                    written += len(chunk)
                    if reporter is not None:
                        reporter.bytes(stage=ProgressStage.INSTALLING_MOD_LOADER, message=f"Extracting {relative.as_posix()}...", current=written, total=total_bytes)
            if len(relative.parts) >= 2 and relative.parts[0].casefold() == "mods" and relative.name.casefold().endswith(".jar"):
                override_mods.append({"fileName": relative.name, "path": relative.as_posix(), "sha1": digest.hexdigest(), "size": file_written})
        return override_mods

    @staticmethod
    def _safe_relative_path(value: str) -> PurePosixPath:
        normalized = str(value).replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if len(normalized) > CurseForgePackInstaller.MAX_PATH_LENGTH or not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe path in CurseForge modpack: {value!r}")
        first = path.parts[0].casefold()
        if ":" in first:
            raise RuntimeError(f"Unsafe Windows path in CurseForge modpack: {value!r}")
        if first in CurseForgePackInstaller.RESERVED_ROOT_NAMES:
            raise RuntimeError(f"Reserved path in CurseForge modpack: {value!r}")
        return path

    @staticmethod
    def _validated_instance_name(value: str) -> str:
        name = str(value).strip()
        if not name or name in {".", ".."} or name.endswith((".", " ")) or not CurseForgePackInstaller.INSTANCE_NAME_PATTERN.fullmatch(name):
            raise RuntimeError("The modpack instance name contains invalid Windows filename characters or is longer than 80 characters.")
        return name
