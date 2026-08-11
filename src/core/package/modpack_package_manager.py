from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.parse import quote, urlparse
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo
import hashlib
import json
import os
import shutil
import stat
import tempfile

from src.config import LAUNCHER_SLUG, VERSION_TAG
from src.core.curseforge.curseforge_pack_installer import CurseForgePackInstaller
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.fs.paths import Paths
from src.core.ftb.ftb_pack_installer import FTBPackInstaller
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.instance.settings_manager import SettingsManager
from src.core.minecraft.version_manager import VersionManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_pack_installer import ModrinthPackInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.package.package_manager import PackageManager
from src.core.package.provider_package_store import ProviderPackageStore
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.package.modpack_export import ModpackExportOptions, ModpackExportResult
from src.models.package.provider_modpack_preview import ProviderModpackPreview
from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_stage import ProgressStage


class ModpackPackageManager:
    PROFILE_FORMAT = "mcw-provider-profile"
    PROFILE_VERSION = 1
    PORTABLE_FORMAT = "mcw-portable-modpack"
    PORTABLE_VERSION = 2
    PROFILE_MANIFEST = "mcw-profile.json"
    PORTABLE_MANIFEST = "mcwpack.json"
    SETTINGS_MEMBER = "mcw/instance-settings.json"
    INSTANCE_ICON_PREFIX = "mcw/instance-icon"
    NATIVE_PREFIX = "provider/"
    OVERRIDES_PREFIX = "overrides/"
    EMBEDDED_PREFIX = "embedded/"
    MANUAL_REGISTRY = "manual-files.json"
    MAX_MANIFEST_BYTES = 8 * 1024 * 1024
    MAX_ARCHIVE_FILES = 100_000
    MAX_ARCHIVE_BYTES = 64 * 1024 * 1024 * 1024
    COPY_CHUNK_SIZE = 1024 * 1024
    DISTRIBUTION_NOTICE = (
        "Users are responsible for ensuring that sharing, publishing, or hosting modpacks complies "
        "with individual mod licenses, provider policies, and applicable rights. MCW Launcher does "
        "not endorse or authorize unauthorized redistribution."
    )

    @staticmethod
    def inspect(package_path: Path) -> ProviderModpackPreview:
        path = Path(package_path)
        if not path.is_file():
            raise RuntimeError(f"Modpack package '{path}' does not exist.")
        try:
            with ZipFile(path, "r") as archive:
                ModpackPackageManager._validate_archive(archive)
                names = {info.filename.replace("\\", "/").strip("/") for info in archive.infolist() if not info.is_dir()}
                if ModpackPackageManager.PROFILE_MANIFEST in names:
                    return ModpackPackageManager._inspect_profile(path, archive)
                if ModpackPackageManager.PORTABLE_MANIFEST in names:
                    return ModpackPackageManager._inspect_portable(path, archive)
                if ModrinthPackInstaller.INDEX_NAME in names:
                    return ModpackPackageManager._inspect_modrinth(path, archive)
                if CurseForgePackInstaller.MANIFEST_NAME in names:
                    return ModpackPackageManager._inspect_curseforge(path, archive)
        except BadZipFile as error:
            raise RuntimeError("The selected modpack package is not a valid ZIP archive.") from error
        raise RuntimeError("Unsupported modpack package. Select a Modrinth .mrpack, CurseForge export ZIP, or MCW provider profile.")

    @staticmethod
    def import_package(package_path: Path, settings_override: dict | None = None, install_optional_files: bool = True, on_progress: ProgressCallback | None = None, instance_name: str = "") -> Instance:
        path = Path(package_path)
        preview = ModpackPackageManager.inspect(path)
        if str(instance_name or "").strip():
            preview = ProviderModpackPreview(
                package_path=preview.package_path,
                provider=preview.provider,
                package_format=preview.package_format,
                name=InstanceManager.validate_name(str(instance_name).strip()),
                version_id=preview.version_id,
                version_label=preview.version_label,
                version_id_source=preview.version_id_source,
                version_id_is_provider_native=preview.version_id_is_provider_native,
                minecraft_version=preview.minecraft_version,
                mod_loader=preview.mod_loader,
                file_count=preview.file_count,
                summary=preview.summary,
                icon=preview.icon,
                settings=preview.settings,
                has_package_settings=preview.has_package_settings,
                install_optional_files=preview.install_optional_files,
                provider_reference=preview.provider_reference,
                native_package_member=preview.native_package_member,
            )
        reporter = ProgressReporter(on_progress)
        reporter.status(ProgressStage.IMPORTING_INSTANCE, f"Reading {preview.provider.title()} modpack package...")
        if preview.package_format == "provider_profile":
            return ModpackPackageManager._import_profile(path, preview, settings_override, install_optional_files, reporter)
        if preview.package_format == "mrpack":
            return ModrinthPackInstaller.install_local_archive(path, preview.name, install_optional_files, reporter, settings_override).instance
        if preview.package_format == "curseforge_zip":
            return CurseForgePackInstaller.install_local_archive(path, preview.name, install_optional_files, reporter, settings_override).instance
        if preview.package_format == "portable_mcwpack":
            return ModpackPackageManager._import_portable(path, preview, settings_override, reporter)
        raise RuntimeError(f"Unsupported modpack package format: {preview.package_format}")

    @staticmethod
    def export(instance: Instance, output_path: Path, options: ModpackExportOptions, on_progress: ProgressCallback | None = None) -> ModpackExportResult:
        normalized = options.normalized()
        if normalized.mode == ModpackExportOptions.PROVIDER_PROFILE:
            return ModpackPackageManager._export_provider_profile(instance, Path(output_path), normalized, on_progress)
        return ModpackPackageManager._export_portable(instance, Path(output_path), normalized, on_progress)

    @staticmethod
    def _inspect_modrinth(path: Path, archive: ZipFile) -> ProviderModpackPreview:
        index = ModrinthPackInstaller._read_index(archive)
        minecraft, loader, loader_version = ModrinthPackInstaller._parse_dependencies(index)
        name = str(index.get("name") or path.stem).strip() or path.stem
        version_label = str(index.get("versionId") or "Imported").strip() or "Imported"
        return ProviderModpackPreview(
            package_path=path,
            provider="modrinth",
            package_format="mrpack",
            name=InstanceManager.next_available_name(InstanceManager.validate_name(name)),
            version_id=minecraft,
            version_label=version_label,
            version_id_source="modrinth.index.json",
            version_id_is_provider_native=True,
            minecraft_version=minecraft,
            mod_loader=(loader, loader_version),
            file_count=len(index.get("files", [])),
            summary=str(index.get("summary") or ""),
            settings=SettingsManager.default_dict(),
            has_package_settings=False,
            provider_reference={"versionId": version_label},
        )

    @staticmethod
    def _inspect_curseforge(path: Path, archive: ZipFile) -> ProviderModpackPreview:
        manifest = CurseForgePackInstaller._read_manifest(archive)
        minecraft, loader, loader_version = CurseForgePackInstaller._parse_loader(manifest)
        name = str(manifest.get("name") or path.stem).strip() or path.stem
        version_label = str(manifest.get("version") or manifest.get("versionName") or "Imported").strip() or "Imported"
        return ProviderModpackPreview(
            package_path=path,
            provider="curseforge",
            package_format="curseforge_zip",
            name=InstanceManager.next_available_name(InstanceManager.validate_name(name)),
            version_id=minecraft,
            version_label=version_label,
            version_id_source="manifest.json",
            version_id_is_provider_native=True,
            minecraft_version=minecraft,
            mod_loader=(loader, loader_version),
            file_count=len(manifest.get("files", [])),
            summary=str(manifest.get("author") or ""),
            settings=SettingsManager.default_dict(),
            has_package_settings=False,
        )

    @staticmethod
    def _inspect_profile(path: Path, archive: ZipFile) -> ProviderModpackPreview:
        profile = ModpackPackageManager._read_json(archive, ModpackPackageManager.PROFILE_MANIFEST)
        if str(profile.get("format") or "").strip() != ModpackPackageManager.PROFILE_FORMAT:
            raise RuntimeError("Invalid MCW provider profile format.")
        if int(profile.get("formatVersion", 0) or 0) > ModpackPackageManager.PROFILE_VERSION:
            raise RuntimeError("The provider profile was created by a newer MCW Launcher.")
        provider = str(profile.get("provider") or "").strip().casefold()
        if provider not in {"modrinth", "curseforge", "ftb"}:
            raise RuntimeError("The provider profile declares an unsupported provider.")
        settings = ModpackPackageManager._read_optional_json(archive, ModpackPackageManager.SETTINGS_MEMBER)
        native_member = str(profile.get("nativePackage") or "").replace("\\", "/").strip("/")
        if native_member:
            info = ModpackPackageManager._member(archive, native_member)
            if info is None or info.file_size > ProviderPackageStore.MAX_NATIVE_PACKAGE_BYTES:
                raise RuntimeError("The provider profile is missing its native package.")
            suffix = ".mrpack" if provider == "modrinth" else ".zip"
            temporary = ModpackPackageManager._copy_member_to_temporary(archive, info, suffix)
            try:
                expected_sha256 = str(profile.get("nativePackageSha256") or "").strip().casefold()
                if expected_sha256 and ProviderPackageStore.sha256(temporary).casefold() != expected_sha256:
                    raise RuntimeError("The provider profile native package checksum does not match.")
                with ZipFile(temporary, "r") as native_archive:
                    ModpackPackageManager._validate_archive(native_archive)
                    if provider == "modrinth":
                        native_preview = ModpackPackageManager._inspect_modrinth(path, native_archive)
                    elif provider == "curseforge":
                        native_preview = ModpackPackageManager._inspect_curseforge(path, native_archive)
                    else:
                        raise RuntimeError("FTB provider profiles use references rather than embedded native packages.")
            finally:
                temporary.unlink(missing_ok=True)
            return ProviderModpackPreview(
                package_path=path,
                provider=provider,
                package_format="provider_profile",
                name=InstanceManager.next_available_name(InstanceManager.validate_name(str(profile.get("instanceName") or native_preview.name))),
                version_id=native_preview.minecraft_version,
                version_label=str(profile.get("packVersion") or native_preview.version_label),
                version_id_source="mcw-profile.json",
                version_id_is_provider_native=True,
                minecraft_version=native_preview.minecraft_version,
                mod_loader=native_preview.mod_loader,
                file_count=native_preview.file_count,
                summary=native_preview.summary,
                icon=ModpackPackageManager._icon_value(profile.get("instanceIcon")),
                settings=SettingsManager.normalize_dict(settings),
                has_package_settings=bool(settings),
                provider_reference=dict(profile.get("providerReference") or {}),
                native_package_member=native_member,
            )
        reference = profile.get("providerReference") if isinstance(profile.get("providerReference"), dict) else {}
        minecraft = str(profile.get("minecraftVersion") or "").strip()
        loader_data = profile.get("modLoader") if isinstance(profile.get("modLoader"), (list, tuple)) else ()
        loader = str(loader_data[0] if len(loader_data) > 0 else "").strip().casefold()
        loader_version = str(loader_data[1] if len(loader_data) > 1 else "").strip()
        if not minecraft or loader not in ModLoaderManager.MODDED_LOADERS:
            raise RuntimeError("The provider profile does not include enough runtime metadata.")
        name = str(profile.get("instanceName") or profile.get("packName") or path.stem).strip()
        return ProviderModpackPreview(
            package_path=path,
            provider=provider,
            package_format="provider_profile",
            name=InstanceManager.next_available_name(InstanceManager.validate_name(name)),
            version_id=minecraft,
            version_label=str(profile.get("packVersion") or "Provider version"),
            version_id_source="mcw-profile.json",
            version_id_is_provider_native=True,
            minecraft_version=minecraft,
            mod_loader=(loader, loader_version),
            file_count=max(0, int(profile.get("fileCount", 0) or 0)),
            summary=str(profile.get("summary") or ""),
            icon=ModpackPackageManager._icon_value(profile.get("instanceIcon")),
            settings=SettingsManager.normalize_dict(settings),
            has_package_settings=bool(settings),
            provider_reference=dict(reference),
        )

    @staticmethod
    def _inspect_portable(path: Path, archive: ZipFile) -> ProviderModpackPreview:
        manifest = ModpackPackageManager._read_json(archive, ModpackPackageManager.PORTABLE_MANIFEST)
        if str(manifest.get("format") or "").strip() != ModpackPackageManager.PORTABLE_FORMAT:
            raise RuntimeError("Invalid portable MCWPack format.")
        if int(manifest.get("formatVersion", 0) or 0) > ModpackPackageManager.PORTABLE_VERSION:
            raise RuntimeError("The portable MCWPack was created by a newer launcher.")
        instance = manifest.get("instance") if isinstance(manifest.get("instance"), dict) else {}
        minecraft = str(instance.get("minecraftVersion") or "").strip()
        loader_data = instance.get("modLoader") if isinstance(instance.get("modLoader"), (list, tuple)) else ()
        loader = str(loader_data[0] if len(loader_data) > 0 else "vanilla").strip().casefold()
        loader_version = str(loader_data[1] if len(loader_data) > 1 else "-1").strip()
        if not minecraft:
            raise RuntimeError("The portable MCWPack does not declare a Minecraft version.")
        settings = ModpackPackageManager._read_optional_json(archive, ModpackPackageManager.SETTINGS_MEMBER)
        files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
        name = str(instance.get("name") or path.stem).strip()
        return ProviderModpackPreview(
            package_path=path,
            provider="mcw",
            package_format="portable_mcwpack",
            name=InstanceManager.next_available_name(InstanceManager.validate_name(name)),
            version_id=minecraft,
            version_label=str(manifest.get("packVersion") or "Portable"),
            version_id_source="mcwpack.json",
            version_id_is_provider_native=False,
            minecraft_version=minecraft,
            mod_loader=(loader, loader_version),
            file_count=len(files),
            summary=str(manifest.get("summary") or ""),
            icon=ModpackPackageManager._icon_value(instance.get("icon")),
            settings=SettingsManager.normalize_dict(settings),
            has_package_settings=bool(settings),
        )

    @staticmethod
    def _import_profile(path: Path, preview: ProviderModpackPreview, settings_override: dict | None, install_optional_files: bool, reporter: ProgressReporter) -> Instance:
        icon_temporary: Path | None = None
        try:
            with ZipFile(path, "r") as archive:
                ModpackPackageManager._validate_archive(archive)
                profile = ModpackPackageManager._read_json(archive, ModpackPackageManager.PROFILE_MANIFEST)
                icon_temporary = ModpackPackageManager._extract_instance_icon(archive, profile.get("instanceIcon"))
                if preview.native_package_member:
                    info = ModpackPackageManager._member(archive, preview.native_package_member)
                    if info is None:
                        raise RuntimeError("The provider profile is missing its native package.")
                    suffix = ".mrpack" if preview.provider == "modrinth" else ".zip"
                    temporary = Paths.instance_staging_root() / f"provider-package-{uuid4().hex}{suffix}"
                    temporary.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with archive.open(info, "r") as source, temporary.open("wb") as destination:
                            shutil.copyfileobj(source, destination, length=ModpackPackageManager.COPY_CHUNK_SIZE)
                        if preview.provider == "modrinth":
                            result = ModrinthPackInstaller.install_local_archive(temporary, preview.name, install_optional_files, reporter, settings_override)
                        else:
                            result = CurseForgePackInstaller.install_local_archive(temporary, preview.name, install_optional_files, reporter, settings_override)
                        return ModpackPackageManager._restore_instance_icon(result.instance, icon_temporary, preview.provider)
                    finally:
                        temporary.unlink(missing_ok=True)

            reference = preview.provider_reference
            if preview.provider == "modrinth":
                project_id = str(reference.get("projectId") or "").strip()
                version_id = str(reference.get("versionId") or "").strip()
                if not project_id or not version_id:
                    raise RuntimeError("The Modrinth provider profile is missing project/version IDs.")
                result = ModrinthPackInstaller.install(project_id, version_id, preview.name, install_optional_files, reporter=reporter, settings_override=settings_override)
            elif preview.provider == "curseforge":
                project_id = int(reference.get("projectId") or 0)
                file_id = int(reference.get("fileId") or 0)
                if project_id <= 0 or file_id <= 0:
                    raise RuntimeError("The CurseForge provider profile is missing project/file IDs.")
                result = CurseForgePackInstaller.install(project_id, file_id, preview.name, install_optional_files, reporter=reporter, settings_override=settings_override)
            elif preview.provider == "ftb":
                project_id = int(reference.get("projectId") or 0)
                version_id = int(reference.get("versionId") or 0)
                if project_id <= 0 or version_id <= 0:
                    raise RuntimeError("The FTB provider profile is missing project/version IDs.")
                result = FTBPackInstaller.install(project_id, version_id, preview.name, install_optional_files, reporter=reporter, settings_override=settings_override)
            else:
                raise RuntimeError("Unsupported provider profile.")
            return ModpackPackageManager._restore_instance_icon(result.instance, icon_temporary, preview.provider)
        finally:
            if icon_temporary is not None:
                icon_temporary.unlink(missing_ok=True)

    @staticmethod
    def _export_provider_profile(instance: Instance, output_path: Path, options: ModpackExportOptions, on_progress: ProgressCallback | None) -> ModpackExportResult:
        origin = ModpackPackageManager._provider_origin(instance)
        provider = str(origin.get("provider") or "").strip().casefold()
        if provider not in {"modrinth", "curseforge", "ftb"}:
            raise RuntimeError("This instance is not managed by a supported Modrinth, CurseForge, or FTB modpack.")
        output = Path(output_path)
        if output.suffix.casefold() != ".zip":
            output = output.with_suffix(".zip")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.part")
        reporter = ProgressReporter(on_progress)
        reporter.status(ProgressStage.EXPORTING_INSTANCE, f"Preparing {provider.title()} provider profile...")
        native = ProviderPackageStore.native_package(instance) or ModpackPackageManager._cached_native_package(provider, origin)
        reference_ready = (
            bool(str(origin.get("projectId") or "").strip() and str(origin.get("versionId") or "").strip())
            if provider in {"modrinth", "ftb"}
            else bool(str(origin.get("projectId") or "").strip() and str(origin.get("fileId") or "").strip())
        )
        if native is None and not reference_ready:
            raise RuntimeError("The original provider package is unavailable and the provider reference is incomplete.")
        settings = ModpackPackageManager._portable_settings(instance)
        icon_metadata, icon_source = ModpackPackageManager._instance_icon_export(instance)
        profile = {
            "format": ModpackPackageManager.PROFILE_FORMAT,
            "formatVersion": ModpackPackageManager.PROFILE_VERSION,
            "createdAt": datetime.now(UTC).isoformat(),
            "exportedBy": LAUNCHER_SLUG,
            "launcherVersion": VERSION_TAG,
            "provider": provider,
            "instanceName": instance.name,
            "packName": str(origin.get("packName") or instance.name),
            "packVersion": str(origin.get("packVersion") or ""),
            "minecraftVersion": instance.version_id,
            "modLoader": list(instance.mod_loader),
            "providerReference": {
                key: origin[key]
                for key in ("projectId", "versionId", "fileId")
                if str(origin.get(key) or "").strip()
            },
            "fileCount": len(ModProvenanceRegistry.entries_by_file(instance)),
            "instanceIcon": icon_metadata,
            "nativePackage": "",
            "nativePackageSha256": "",
            "distributionNotice": ModpackPackageManager.DISTRIBUTION_NOTICE,
        }
        try:
            temporary.unlink(missing_ok=True)
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
                if native is not None and native.is_file():
                    suffix = ".mrpack" if provider == "modrinth" else ".zip"
                    member = f"{ModpackPackageManager.NATIVE_PREFIX}original-package{suffix}"
                    profile["nativePackage"] = member
                    profile["nativePackageSha256"] = ProviderPackageStore.sha256(native)
                    archive.write(native, member)
                if icon_source is not None:
                    archive.write(icon_source, str(icon_metadata["member"]))
                archive.writestr(ModpackPackageManager.PROFILE_MANIFEST, ModpackPackageManager._json_bytes(profile))
                archive.writestr(ModpackPackageManager.SETTINGS_MEMBER, ModpackPackageManager._json_bytes(settings))
                archive.writestr("DISTRIBUTION-NOTICE.txt", ModpackPackageManager.DISTRIBUTION_NOTICE + "\n")
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            temporary.replace(output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        reporter.succeeded(ProgressStage.EXPORTING_INSTANCE, f"Provider profile exported to {output.name}.")
        return ModpackExportResult(output_path=output, mode=options.mode, native_package_included=native is not None)

    @staticmethod
    def _export_portable(instance: Instance, output_path: Path, options: ModpackExportOptions, on_progress: ProgressCallback | None) -> ModpackExportResult:
        output = Path(output_path)
        if output.suffix.casefold() != ".mcwpack":
            output = output.with_suffix(".mcwpack")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.part")
        reporter = ProgressReporter(on_progress)
        reporter.status(ProgressStage.EXPORTING_INSTANCE, f"Scanning portable content for '{instance.name}'...")
        root = Path(instance.instance_dir)
        provenance = ModpackPackageManager._portable_mod_inventory(instance)
        entries: list[dict] = []
        embedded: list[tuple[Path, str]] = []
        referenced = 0
        manual = 0
        for item in provenance:
            relative = str(item.get("path") or f"mods/{item.get('fileName') or ''}").replace("\\", "/").strip("/")
            safe = ModpackPackageManager._safe_relative(relative)
            if safe is None or not safe.as_posix().casefold().startswith("mods/"):
                continue
            target = root.joinpath(*safe.parts)
            sources = ModpackPackageManager._sources_for_provenance(item)
            delivery = "referenced" if sources else "manual"
            if options.portable_mode == ModpackExportOptions.FULL and target.is_file() and str(item.get("provider") or "").casefold() != "optifine":
                delivery = "embedded"
            elif delivery == "manual" and bool(item.get("redistributionAllowed", False)) and target.is_file():
                delivery = "embedded"
            entry = {
                "contentType": "mod",
                "targetPath": safe.as_posix(),
                "fileName": Path(str(item.get("fileName") or safe.name)).name,
                "delivery": delivery,
                "provider": str(item.get("provider") or "unknown").strip().casefold(),
                "projectId": str(item.get("projectId") or "").strip(),
                "versionId": str(item.get("versionId") or "").strip(),
                "fileId": str(item.get("fileId") or "").strip(),
                "versionNumber": str(item.get("versionNumber") or "").strip(),
                "size": max(0, int(item.get("size", 0) or (target.stat().st_size if target.is_file() else 0))),
                "hashes": {key: value for key, value in {"sha1": str(item.get("sha1") or "").strip().casefold(), "sha512": str(item.get("sha512") or "").strip().casefold()}.items() if value},
                "sources": sources,
                "projectUrl": str(item.get("projectUrl") or "").strip(),
                "projectName": str(item.get("projectName") or item.get("title") or item.get("fileName") or safe.name).strip(),
                "manualReason": str(item.get("manualReason") or "Automatic download is unavailable or redistribution is not permitted.").strip(),
                "managedByModpack": bool(item.get("managedByModpack", False)),
                "enabled": bool(item.get("enabled", not safe.name.casefold().endswith(".disabled"))),
                "license": {
                    "id": str(item.get("licenseId") or "").strip(),
                    "name": str(item.get("licenseName") or "").strip(),
                    "url": str(item.get("licenseUrl") or "").strip(),
                    "redistributionAllowed": bool(item.get("redistributionAllowed", False)),
                },
            }
            if delivery == "embedded":
                if not target.is_file():
                    entry["delivery"] = "referenced" if sources else "manual"
                else:
                    member = f"{ModpackPackageManager.EMBEDDED_PREFIX}{safe.as_posix()}"
                    entry["embeddedPath"] = member
                    embedded.append((target, member))
            if entry["delivery"] == "referenced":
                referenced += 1
            elif entry["delivery"] == "manual":
                manual += 1
            entries.append(entry)

        override_files = ModpackPackageManager._portable_override_files(instance, options.include_saves)
        icon_metadata, icon_source = ModpackPackageManager._instance_icon_export(instance)
        manifest = {
            "format": ModpackPackageManager.PORTABLE_FORMAT,
            "formatVersion": ModpackPackageManager.PORTABLE_VERSION,
            "createdAt": datetime.now(UTC).isoformat(),
            "launcherVersion": VERSION_TAG,
            "portableMode": options.portable_mode,
            "instance": {
                "name": instance.name,
                "minecraftVersion": instance.version_id,
                "modLoader": list(instance.mod_loader),
                "icon": icon_metadata,
            },
            "files": entries,
            "overridesPrefix": ModpackPackageManager.OVERRIDES_PREFIX,
            "distributionNotice": ModpackPackageManager.DISTRIBUTION_NOTICE,
        }
        total = len(entries) + len(override_files) + len(embedded) + 3 + (1 if icon_source is not None else 0)
        current = 0
        reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
        try:
            temporary.unlink(missing_ok=True)
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
                archive.writestr(ModpackPackageManager.PORTABLE_MANIFEST, ModpackPackageManager._json_bytes(manifest))
                current += 1
                reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
                archive.writestr(ModpackPackageManager.SETTINGS_MEMBER, ModpackPackageManager._json_bytes(ModpackPackageManager._portable_settings(instance)))
                current += 1
                reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
                archive.writestr("DISTRIBUTION-NOTICE.txt", ModpackPackageManager.DISTRIBUTION_NOTICE + "\n")
                current += 1
                if icon_source is not None:
                    archive.write(icon_source, str(icon_metadata["member"]))
                    current += 1
                    reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
                for source, relative in override_files:
                    archive.write(source, f"{ModpackPackageManager.OVERRIDES_PREFIX}{relative}")
                    current += 1
                    reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
                for source, member in embedded:
                    archive.write(source, member)
                    current += 1
                    reporter.files(ProgressStage.EXPORTING_INSTANCE, "Exporting portable modpack...", current, total)
            with temporary.open("r+b") as stream:
                os.fsync(stream.fileno())
            temporary.replace(output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        reporter.succeeded(ProgressStage.EXPORTING_INSTANCE, f"Portable MCWPack exported to {output.name}.")
        return ModpackExportResult(output_path=output, mode=options.mode, referenced_files=referenced, embedded_files=len(embedded), manual_files=manual)

    @staticmethod
    def _import_portable(path: Path, preview: ProviderModpackPreview, settings_override: dict | None, reporter: ProgressReporter) -> Instance:
        staging = Paths.instance_staging_root() / f"portable-import-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        created: Instance | None = None
        icon_temporary: Path | None = None
        try:
            with ZipFile(path, "r") as archive:
                ModpackPackageManager._validate_archive(archive)
                manifest = ModpackPackageManager._read_json(archive, ModpackPackageManager.PORTABLE_MANIFEST)
                instance_manifest = manifest.get("instance") if isinstance(manifest.get("instance"), dict) else {}
                icon_temporary = ModpackPackageManager._extract_instance_icon(archive, instance_manifest.get("icon"))
                version = VersionManager.load(preview.minecraft_version)
                loader = ModLoaderManager.resolve(preview.minecraft_version, preview.mod_loader[0], preview.mod_loader[1])
                created = InstanceManager.create(preview.name, version, loader)
                SettingsManager.save_dict(created, settings_override if settings_override is not None else preview.settings)
                ModpackPackageManager._extract_prefixed(archive, ModpackPackageManager.OVERRIDES_PREFIX, Path(created.instance_dir), reporter)
                ModpackPackageManager._extract_embedded(archive, manifest, Path(created.instance_dir), reporter)
                ModpackPackageManager._write_portable_registries(created, manifest)
                ModProvenanceRegistry.synchronize(created)
                origin = {
                    "provider": "mcw",
                    "packageFormat": "portable_mcwpack",
                    "packName": preview.name,
                    "packVersion": preview.version_label,
                    "source": "local_import",
                }
                ProviderPackageStore.save_origin(created, origin)
                if icon_temporary is not None:
                    created = ModpackPackageManager._restore_instance_icon(created, icon_temporary, "mcw")
                else:
                    created = ModpackPackageManager._restore_legacy_portable_icon(created, instance_manifest.get("icon"))
                return InstanceManager.load(created.name)
        except Exception:
            if created is not None:
                InstanceManager.delete_instance(created.name)
            raise
        finally:
            if icon_temporary is not None:
                icon_temporary.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _write_portable_registries(instance: Instance, manifest: dict) -> None:
        modrinth = ModrinthRegistry.empty()
        curseforge = CurseForgeRegistry.empty()
        ftb_entries: list[dict] = []
        manual_entries: list[dict] = []
        referenced_entries: list[dict] = []
        provenance_entries: list[dict] = []
        disabled_entries: list[dict] = []
        for raw in manifest.get("files", []):
            if not isinstance(raw, dict) or str(raw.get("contentType") or "mod").casefold() != "mod":
                continue
            target = ModpackPackageManager._safe_relative(str(raw.get("targetPath") or ""))
            if target is None:
                continue
            delivery = str(raw.get("delivery") or "manual").casefold()
            provider = str(raw.get("provider") or "unknown").casefold()
            sources = raw.get("sources") if isinstance(raw.get("sources"), list) else []
            source = next((item for item in sources if isinstance(item, dict) and str(item.get("provider") or "").casefold() == provider), {})
            filename = Path(str(raw.get("fileName") or target.name)).name
            enabled = bool(raw.get("enabled", not target.name.casefold().endswith(".disabled")))
            hashes = raw.get("hashes") if isinstance(raw.get("hashes"), dict) else {}
            if not enabled and delivery == "referenced":
                disabled_entries.append({"targetPath": target.as_posix(), "fileName": filename, "size": max(0, int(raw.get("size", 0) or 0)), "hashes": {key: str(value) for key, value in hashes.items() if str(value).strip()}})
            provenance_entries.append({
                "fileName": filename,
                "path": target.as_posix(),
                "provider": provider,
                "projectId": str(raw.get("projectId") or source.get("projectId") or "").strip(),
                "versionId": str(raw.get("versionId") or source.get("versionId") or "").strip(),
                "fileId": str(raw.get("fileId") or source.get("fileId") or "").strip(),
                "versionNumber": str(raw.get("versionNumber") or "").strip(),
                "sha1": str(hashes.get("sha1") or "").strip(),
                "sha512": str(hashes.get("sha512") or "").strip(),
                "size": max(0, int(raw.get("size", 0) or 0)),
                "downloadUrls": [str(url).strip() for item in sources if isinstance(item, dict) for url in item.get("urls", []) if str(url).strip()],
                "sources": [dict(item) for item in sources if isinstance(item, dict)],
                "projectUrl": str(raw.get("projectUrl") or "").strip(),
                "licenseId": str((raw.get("license") or {}).get("id") or "") if isinstance(raw.get("license"), dict) else "",
                "licenseName": str((raw.get("license") or {}).get("name") or "") if isinstance(raw.get("license"), dict) else "",
                "licenseUrl": str((raw.get("license") or {}).get("url") or "") if isinstance(raw.get("license"), dict) else "",
                "redistributionAllowed": bool((raw.get("license") or {}).get("redistributionAllowed", False)) if isinstance(raw.get("license"), dict) else False,
                "managedByModpack": True,
                "packProvider": "mcw",
            })
            if delivery == "embedded":
                continue
            if delivery == "referenced":
                referenced_entries.append({
                    "targetPath": target.as_posix(),
                    "fileName": filename,
                    "size": max(0, int(raw.get("size", 0) or 0)),
                    "hashes": {key: str(value) for key, value in hashes.items() if str(value).strip()},
                    "sources": [dict(item) for item in sources if isinstance(item, dict)],
                })
            if provider == "modrinth":
                project_id = str(raw.get("projectId") or source.get("projectId") or "").strip()
                version_id = str(raw.get("versionId") or source.get("versionId") or "").strip()
                if project_id:
                    modrinth["mods"][project_id] = {
                        "projectId": project_id,
                        "versionId": version_id,
                        "versionNumber": str(raw.get("versionNumber") or "Portable"),
                        "fileName": filename,
                        "sha1": str(hashes.get("sha1") or ""),
                        "sha512": str(hashes.get("sha512") or ""),
                        "size": max(0, int(raw.get("size", 0) or 0)),
                        "downloadUrls": list(dict.fromkeys(str(url).strip() for item in sources if isinstance(item, dict) for url in item.get("urls", []) if str(url).strip())),
                        "pendingDownload": True,
                        "title": filename,
                    }
                    continue
            elif provider == "curseforge":
                project_id = int(raw.get("projectId") or source.get("projectId") or 0)
                file_id = int(raw.get("fileId") or source.get("fileId") or 0)
                if project_id > 0 and file_id > 0:
                    curseforge["mods"][str(project_id)] = {
                        "projectId": project_id,
                        "fileId": file_id,
                        "fileName": filename,
                        "displayName": filename,
                        "sha1": str(hashes.get("sha1") or ""),
                        "size": max(0, int(raw.get("size", 0) or 0)),
                        "downloadUrl": next((str(url) for item in sources if isinstance(item, dict) for url in item.get("urls", []) if str(url).strip()), ""),
                        "pendingDownload": True,
                    }
                    continue
            elif provider == "ftb":
                file_id = int(raw.get("fileId") or source.get("fileId") or 0)
                if file_id > 0:
                    ftb_entries.append({
                        "fileId": file_id,
                        "fileName": filename,
                        "path": target.as_posix(),
                        "sha1": str(hashes.get("sha1") or ""),
                        "size": max(0, int(raw.get("size", 0) or 0)),
                        "urls": list(dict.fromkeys(str(url).strip() for item in sources if isinstance(item, dict) for url in item.get("urls", []) if str(url).strip())),
                        "pendingDownload": True,
                        "provider": "ftb",
                    })
                    continue
            manual_entries.append({
                "targetPath": target.as_posix(),
                "fileName": filename,
                "provider": provider,
                "projectId": str(raw.get("projectId") or source.get("projectId") or "").strip(),
                "versionId": str(raw.get("versionId") or source.get("versionId") or "").strip(),
                "fileId": str(raw.get("fileId") or source.get("fileId") or "").strip(),
                "projectName": str(raw.get("projectName") or filename).strip(),
                "projectUrl": str(raw.get("projectUrl") or "").strip(),
                "versionUrl": str(raw.get("versionUrl") or "").strip(),
                "reason": str(raw.get("manualReason") or "Automatic download is unavailable or redistribution is not permitted.").strip(),
                "size": max(0, int(raw.get("size", 0) or 0)),
                "hashes": {key: str(value) for key, value in hashes.items() if str(value).strip()},
            })
        if modrinth["mods"]:
            ModrinthRegistry.save(instance, modrinth)
        if curseforge["mods"]:
            CurseForgeRegistry.save(instance, curseforge)
        if ftb_entries:
            FTBPackRegistry.save(instance, {"projectId": 0, "versionId": 0, "name": instance.name, "managedFiles": ftb_entries})
        if manual_entries:
            path = Path(instance.instance_dir) / ".mcw" / ModpackPackageManager.MANUAL_REGISTRY
            ModpackPackageManager._write_registry(path, {"schemaVersion": 1, "files": manual_entries})
        if referenced_entries:
            path = Path(instance.instance_dir) / ".mcw" / "portable-referenced-files.json"
            ModpackPackageManager._write_registry(path, {"schemaVersion": 1, "files": referenced_entries})
        if disabled_entries:
            path = Path(instance.instance_dir) / ".mcw" / "portable-disabled-files.json"
            ModpackPackageManager._write_registry(path, {"schemaVersion": 1, "files": disabled_entries})
        if provenance_entries:
            ModProvenanceRegistry.record_many(instance, provenance_entries)

    @staticmethod
    def _extract_embedded(archive: ZipFile, manifest: dict, destination: Path, reporter: ProgressReporter) -> None:
        embedded = [item for item in manifest.get("files", []) if isinstance(item, dict) and str(item.get("delivery") or "").casefold() == "embedded"]
        total = len(embedded)
        for index, item in enumerate(embedded, start=1):
            target_relative = ModpackPackageManager._safe_relative(str(item.get("targetPath") or ""))
            member_name = str(item.get("embeddedPath") or "").replace("\\", "/").strip("/")
            if target_relative is None or not member_name.startswith(ModpackPackageManager.EMBEDDED_PREFIX):
                raise RuntimeError("The portable MCWPack contains an unsafe embedded file entry.")
            info = ModpackPackageManager._member(archive, member_name)
            if info is None:
                raise RuntimeError(f"The portable MCWPack is missing embedded file '{member_name}'.")
            target = destination.joinpath(*target_relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=ModpackPackageManager.COPY_CHUNK_SIZE)
            hashes = item.get("hashes") if isinstance(item.get("hashes"), dict) else {}
            if not ModpackPackageManager._verify_file(target, max(0, int(item.get("size", 0) or 0)), hashes):
                target.unlink(missing_ok=True)
                raise RuntimeError(f"Embedded file verification failed: {target_relative.as_posix()}")
            reporter.files(ProgressStage.IMPORTING_INSTANCE, "Importing embedded mod files...", index, total)

    @staticmethod
    def _extract_prefixed(archive: ZipFile, prefix: str, destination: Path, reporter: ProgressReporter) -> None:
        normalized = prefix.strip("/") + "/"
        entries = [info for info in archive.infolist() if not info.is_dir() and info.filename.replace("\\", "/").startswith(normalized)]
        total = len(entries)
        for index, info in enumerate(entries, start=1):
            raw = info.filename.replace("\\", "/")[len(normalized):]
            relative = ModpackPackageManager._safe_relative(raw)
            if relative is None:
                raise RuntimeError(f"Unsafe path in modpack overrides: {info.filename}")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=ModpackPackageManager.COPY_CHUNK_SIZE)
            reporter.files(ProgressStage.IMPORTING_INSTANCE, "Importing modpack overrides...", index, total)

    @staticmethod
    def _provider_origin(instance: Instance) -> dict:
        stored = ProviderPackageStore.load_origin(instance)
        if stored.get("provider"):
            return stored
        modrinth = ModrinthPackRegistry.load(instance)
        if modrinth:
            return {
                "provider": "modrinth",
                "projectId": str(modrinth.get("projectId") or ""),
                "versionId": str(modrinth.get("versionId") or ""),
                "packName": str(modrinth.get("name") or instance.name),
                "packVersion": str(modrinth.get("versionNumber") or ""),
            }
        curseforge = CurseForgePackRegistry.load(instance)
        if curseforge:
            return {
                "provider": "curseforge",
                "projectId": str(curseforge.get("projectId") or ""),
                "fileId": str(curseforge.get("fileId") or ""),
                "packName": str(curseforge.get("name") or instance.name),
                "packVersion": str(curseforge.get("versionName") or ""),
            }
        ftb = FTBPackRegistry.load(instance)
        if ftb:
            return {
                "provider": "ftb",
                "projectId": str(ftb.get("projectId") or ""),
                "versionId": str(ftb.get("versionId") or ""),
                "packName": str(ftb.get("name") or instance.name),
                "packVersion": str(ftb.get("versionName") or ""),
            }
        return {}

    @staticmethod
    def _cached_native_package(provider: str, origin: dict) -> Path | None:
        if provider == "modrinth":
            project = quote(str(origin.get("projectId") or "").strip(), safe="")
            version = quote(str(origin.get("versionId") or "").strip(), safe="")
            directory = Paths.modrinth_root() / "files" / project / version
            candidates = sorted(directory.glob("*.mrpack")) if directory.is_dir() else []
            return candidates[0] if candidates else None
        if provider == "curseforge":
            project = str(origin.get("projectId") or "").strip()
            file_id = str(origin.get("fileId") or "").strip()
            directory = Paths.curseforge_root() / "files" / project / file_id
            candidates = sorted(directory.glob("*.zip")) if directory.is_dir() else []
            return candidates[0] if candidates else None
        return None

    @staticmethod
    def _icon_value(value: object) -> str:
        if isinstance(value, dict):
            return str(value.get("value") or InstanceManager.DEFAULT_ICON).strip() or InstanceManager.DEFAULT_ICON
        return str(value or InstanceManager.DEFAULT_ICON).strip() or InstanceManager.DEFAULT_ICON

    @staticmethod
    def _instance_icon_export(instance: Instance) -> tuple[dict, Path | None]:
        source = InstanceManager.resolve_icon_path(instance)
        if source is None:
            return {"value": InstanceManager.DEFAULT_ICON, "member": "", "sha256": "", "size": 0}, None
        try:
            size = source.stat().st_size
        except OSError:
            return {"value": InstanceManager.DEFAULT_ICON, "member": "", "sha256": "", "size": 0}, None
        suffix = source.suffix.casefold()
        if suffix not in InstanceManager.ICON_EXTENSIONS or size <= 0 or size > InstanceManager.MAX_ICON_BYTES:
            return {"value": InstanceManager.DEFAULT_ICON, "member": "", "sha256": "", "size": 0}, None
        member = f"{ModpackPackageManager.INSTANCE_ICON_PREFIX}{suffix}"
        return {
            "value": str(instance.icon or InstanceManager.DEFAULT_ICON),
            "member": member,
            "sha256": ProviderPackageStore.sha256(source),
            "size": size,
        }, source

    @staticmethod
    def _extract_instance_icon(archive: ZipFile, value: object) -> Path | None:
        if not isinstance(value, dict):
            return None
        member_name = str(value.get("member") or "").replace("\\", "/").strip("/")
        if not member_name:
            return None
        relative = ModpackPackageManager._safe_relative(member_name)
        if relative is None or not relative.as_posix().casefold().startswith(ModpackPackageManager.INSTANCE_ICON_PREFIX.casefold()):
            raise RuntimeError("The modpack package declares an unsafe instance icon path.")
        info = ModpackPackageManager._member(archive, relative.as_posix())
        if info is None:
            raise RuntimeError("The modpack package is missing its instance icon.")
        expected_size = max(0, int(value.get("size", 0) or 0))
        actual_size = max(0, int(info.file_size or 0))
        if actual_size <= 0 or actual_size > InstanceManager.MAX_ICON_BYTES or (expected_size > 0 and actual_size != expected_size):
            raise RuntimeError("The modpack package instance icon has an invalid size.")
        suffix = Path(relative.name).suffix.casefold()
        if suffix not in InstanceManager.ICON_EXTENSIONS:
            raise RuntimeError("The modpack package instance icon uses an unsupported format.")
        temporary = ModpackPackageManager._copy_member_to_temporary(archive, info, suffix)
        try:
            expected_sha256 = str(value.get("sha256") or "").strip().casefold()
            if expected_sha256 and ProviderPackageStore.sha256(temporary).casefold() != expected_sha256:
                raise RuntimeError("The modpack package instance icon checksum does not match.")
            detected = InstanceArtworkManager._detect_extension(temporary)
            suffix_matches = detected == suffix or {detected, suffix} <= {".jpg", ".jpeg"}
            if not suffix_matches:
                raise RuntimeError("The modpack package instance icon content does not match its file extension.")
            return temporary
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _restore_instance_icon(instance: Instance, icon_temporary: Path | None, package_provider: str) -> Instance:
        if icon_temporary is None:
            return InstanceManager.load(instance.name)
        return InstanceManager.set_icon(
            instance.name,
            icon_temporary,
            origin={"provider": "mcw-package", "package_provider": str(package_provider or "mcw").strip().casefold()},
        )

    @staticmethod
    def _restore_legacy_portable_icon(instance: Instance, value: object) -> Instance:
        if not isinstance(value, str):
            return InstanceManager.load(instance.name)
        relative = ModpackPackageManager._safe_relative(value)
        if relative is None:
            return InstanceManager.load(instance.name)
        candidate = Path(instance.instance_dir).joinpath(*relative.parts)
        if not candidate.is_file() or candidate.suffix.casefold() not in InstanceManager.ICON_EXTENSIONS:
            return InstanceManager.load(instance.name)
        return InstanceManager.set_icon(
            instance.name,
            candidate,
            origin={"provider": "mcw-package", "package_provider": "legacy-portable"},
        )

    @staticmethod
    def _portable_settings(instance: Instance) -> dict:
        settings = SettingsManager.to_dict(SettingsManager.load(instance))
        settings["java"]["path"] = ""
        return settings

    @staticmethod
    def _portable_mod_inventory(instance: Instance) -> list[dict]:
        root = Path(instance.instance_dir)
        mods_dir = root / "mods"
        provenance = ModProvenanceRegistry.entries_by_file(instance)
        inventory: list[dict] = []
        seen: set[str] = set()
        physical_by_base: dict[str, list[Path]] = {}
        if mods_dir.is_dir():
            for path in sorted(mods_dir.iterdir(), key=lambda candidate: candidate.name.casefold()):
                if not path.is_file() or path.is_symlink():
                    continue
                lowered = path.name.casefold()
                if not (lowered.endswith(".jar") or lowered.endswith(".jar.disabled")):
                    continue
                base_name = path.name[:-len(".disabled")] if lowered.endswith(".disabled") else path.name
                physical_by_base.setdefault(base_name.casefold(), []).append(path)
        ambiguous = [paths for paths in physical_by_base.values() if len(paths) > 1]
        if ambiguous:
            names = ", ".join(sorted(path.name for paths in ambiguous for path in paths))
            raise RuntimeError(f"The mods directory contains both enabled and disabled copies of the same mod: {names}")
        for key, paths in physical_by_base.items():
            path = paths[0]
            base_name = path.name[:-len(".disabled")] if path.name.casefold().endswith(".disabled") else path.name
            raw = dict(provenance.get(key) or {})
            raw.setdefault("provider", "local")
            raw["fileName"] = base_name
            raw["path"] = path.relative_to(root).as_posix()
            raw["enabled"] = not path.name.casefold().endswith(".disabled")
            raw["size"] = path.stat().st_size
            raw.update(ModpackPackageManager._hash_file(path))
            inventory.append(raw)
            seen.add(key)
        for key, raw in provenance.items():
            if key in seen:
                continue
            candidate = dict(raw)
            relative = str(candidate.get("path") or f"mods/{candidate.get('fileName') or ''}").replace("\\", "/").strip("/")
            candidate["path"] = relative
            candidate["enabled"] = not PurePosixPath(relative).name.casefold().endswith(".disabled")
            inventory.append(candidate)
        inventory.sort(key=lambda item: str(item.get("path") or item.get("fileName") or "").casefold())
        return inventory

    @staticmethod
    def _hash_file(path: Path) -> dict[str, str]:
        sha1 = hashlib.sha1(usedforsecurity=False)
        sha512 = hashlib.sha512()
        with path.open("rb") as stream:
            while chunk := stream.read(ModpackPackageManager.COPY_CHUNK_SIZE):
                sha1.update(chunk)
                sha512.update(chunk)
        return {"sha1": sha1.hexdigest(), "sha512": sha512.hexdigest()}

    @staticmethod
    def _copy_member_to_temporary(archive: ZipFile, info: ZipInfo, suffix: str) -> Path:
        handle, name = tempfile.mkstemp(prefix="mcw-provider-package-", suffix=suffix)
        os.close(handle)
        destination = Path(name)
        try:
            with archive.open(info, "r") as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=ModpackPackageManager.COPY_CHUNK_SIZE)
                output.flush()
                os.fsync(output.fileno())
            return destination
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    @staticmethod
    def _write_registry(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    @staticmethod
    def _portable_override_files(instance: Instance, include_saves: bool) -> list[tuple[Path, str]]:
        root = Path(instance.instance_dir)
        ignored_roots = {"mods", "logs", "crash-reports"}
        ignored_files = {"instance.json", "settings.json"}
        ignored_mcw = {"mod-provenance.json", "modrinth.json", "curseforge.json", "modrinth-pack.json", "curseforge-pack.json", "ftb-pack.json", "atlauncher-pack.json", "optifine.json", "optifine-profile.json", "content-library.json", "manual-files.json", "portable-disabled-files.json", "portable-referenced-files.json"}
        output: list[tuple[Path, str]] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            parts = PurePosixPath(relative).parts
            if not parts:
                continue
            first = parts[0].casefold()
            if first in ignored_roots or relative.casefold() in ignored_files:
                continue
            if first == "saves" and not include_saves:
                continue
            if first == ".mcw" and len(parts) > 1 and (parts[1].casefold() in ignored_mcw or parts[1].casefold() == "provider" or parts[1].casefold().startswith(f"{InstanceManager.ICON_BASENAME}.")):
                continue
            output.append((path, relative))
        output.sort(key=lambda item: item[1].casefold())
        return output

    @staticmethod
    def _sources_for_provenance(item: dict) -> list[dict]:
        def safe_urls(values: object) -> list[str]:
            output: list[str] = []
            if not isinstance(values, (list, tuple)):
                return output
            for value in values:
                url = str(value or "").strip()
                try:
                    parsed = urlparse(url)
                except ValueError:
                    continue
                if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
                    continue
                if url not in output:
                    output.append(url)
            return output

        sources: list[dict] = []
        raw_sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        for priority, raw in enumerate(raw_sources, start=1):
            if not isinstance(raw, dict):
                continue
            provider = str(raw.get("provider") or "unknown").strip().casefold()
            source = {
                "provider": provider,
                "projectId": str(raw.get("projectId") or "").strip(),
                "versionId": str(raw.get("versionId") or "").strip(),
                "fileId": str(raw.get("fileId") or "").strip(),
                "urls": safe_urls(raw.get("urls", [])),
                "priority": max(1, int(raw.get("priority", priority * 10) or priority * 10)),
            }
            if any((source["projectId"], source["versionId"], source["fileId"], source["urls"])):
                sources.append(source)
        provider = str(item.get("provider") or "unknown").strip().casefold()
        primary = {
            "provider": provider,
            "projectId": str(item.get("projectId") or "").strip(),
            "versionId": str(item.get("versionId") or "").strip(),
            "fileId": str(item.get("fileId") or "").strip(),
            "urls": safe_urls(item.get("downloadUrls", [])),
            "priority": 10,
        }
        if provider in {"modrinth", "curseforge", "ftb"} and any((primary["projectId"], primary["versionId"], primary["fileId"], primary["urls"])):
            identity = (primary["provider"], primary["projectId"], primary["versionId"], primary["fileId"], tuple(primary["urls"]))
            known = {(source["provider"], source["projectId"], source["versionId"], source["fileId"], tuple(source["urls"])) for source in sources}
            if identity not in known:
                sources.insert(0, primary)
        sources.sort(key=lambda source: (int(source.get("priority", 1000)), str(source.get("provider", ""))))
        return sources

    @staticmethod
    def _validate_archive(archive: ZipFile) -> None:
        seen: dict[str, ZipInfo] = {}
        total = 0
        count = 0
        for info in archive.infolist():
            if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
                raise RuntimeError(f"Symbolic links are not allowed in modpack packages: {info.filename}")
            relative = ModpackPackageManager._safe_relative(info.filename)
            if relative is None:
                raise RuntimeError(f"Unsafe path in modpack package: {info.filename}")
            key = relative.as_posix().casefold()
            previous = seen.get(key)
            if previous is not None and not PackageManager._duplicate_members_match(previous, info):
                raise RuntimeError(f"Conflicting duplicate entry in modpack package: {relative.as_posix()}")
            seen[key] = info
            if not info.is_dir():
                count += 1
                total += max(0, int(info.file_size or 0))
                if count > ModpackPackageManager.MAX_ARCHIVE_FILES:
                    raise RuntimeError("The modpack package contains too many files.")
                if total > ModpackPackageManager.MAX_ARCHIVE_BYTES:
                    raise RuntimeError("The modpack package exceeds the extraction safety limit.")

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath | None:
        try:
            return PackageManager._safe_relative_path(str(value or ""))
        except RuntimeError:
            return None

    @staticmethod
    def _read_json(archive: ZipFile, name: str) -> dict:
        info = ModpackPackageManager._member(archive, name)
        if info is None:
            raise RuntimeError(f"Modpack package is missing {name}.")
        if info.file_size > ModpackPackageManager.MAX_MANIFEST_BYTES:
            raise RuntimeError(f"{name} is too large to process safely.")
        try:
            value = json.loads(archive.read(info).decode("utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid {name}: {error}") from error
        if not isinstance(value, dict):
            raise RuntimeError(f"{name} must contain an object.")
        return value

    @staticmethod
    def _read_optional_json(archive: ZipFile, name: str) -> dict:
        return ModpackPackageManager._read_json(archive, name) if ModpackPackageManager._member(archive, name) is not None else {}

    @staticmethod
    def _member(archive: ZipFile, name: str) -> ZipInfo | None:
        normalized = str(name).replace("\\", "/").strip("/").casefold()
        matches = [info for info in archive.infolist() if info.filename.replace("\\", "/").strip("/").casefold() == normalized and not info.is_dir()]
        if len(matches) > 1:
            first = matches[0]
            if any(not PackageManager._duplicate_members_match(first, other) for other in matches[1:]):
                raise RuntimeError(f"Conflicting duplicate archive member: {name}")
        return matches[0] if matches else None

    @staticmethod
    def _json_bytes(value: dict) -> bytes:
        return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    @staticmethod
    def _verify_file(path: Path, expected_size: int, hashes: dict) -> bool:
        try:
            if expected_size > 0 and path.stat().st_size != expected_size:
                return False
        except OSError:
            return False
        sha512 = str(hashes.get("sha512") or "").strip().casefold()
        sha1 = str(hashes.get("sha1") or "").strip().casefold()
        if not sha512 and not sha1:
            return path.is_file()
        digest512 = hashlib.sha512() if sha512 else None
        digest1 = hashlib.sha1(usedforsecurity=False) if sha1 else None
        with path.open("rb") as stream:
            while chunk := stream.read(ModpackPackageManager.COPY_CHUNK_SIZE):
                if digest512 is not None:
                    digest512.update(chunk)
                if digest1 is not None:
                    digest1.update(chunk)
        return (digest512 is None or digest512.hexdigest().casefold() == sha512) and (digest1 is None or digest1.hexdigest().casefold() == sha1)
