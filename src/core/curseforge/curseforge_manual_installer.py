from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib

from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.network.artifact_download_service import artifact_download_service
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.curseforge.manual_import_result import CurseForgeManualImportedFile, CurseForgeManualImportResult
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactRequest


class CurseForgeManualInstaller:
    @staticmethod
    def install(instance: Instance, requirement: CurseForgeManualDownload, source: Path, launch_lock_token: str | None = None) -> str:
        path = Path(source)
        owns_preparing_lock = InstanceRunLock.owns_preparing_lock(instance, launch_lock_token)
        if InstanceRunLock.is_active(instance) and not owns_preparing_lock:
            raise RuntimeError("Close Minecraft before importing a manually downloaded file.")
        if not path.is_file():
            raise RuntimeError("The selected CurseForge file does not exist.")

        if requirement.managed_kind == "pack":
            return CurseForgeManualInstaller._install_pack_file(instance, requirement, path, allow_while_paused=owns_preparing_lock)

        if Path(requirement.file_name).suffix.casefold() != ".jar":
            raise RuntimeError("A standalone mod must be a .jar file.")
        cache = Paths.curseforge_file_cache(requirement.project_id, requirement.file_id, requirement.file_name)
        artifact_download_service.accept_manual_file(CurseForgeManualInstaller._request(requirement, cache), path, allow_while_paused=owns_preparing_lock)
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        metadata = ModManager.read_mod(cache, preferred_loader=loader_name)
        compatibility_warning = ModManager.compatibility_warning(instance, metadata)
        added = ModManager.add_mods(instance, [cache], replace=True, launch_lock_token=launch_lock_token, allow_unverified=True, managed_source=True)
        if not added:
            raise RuntimeError("The selected file could not be added to the instance.")
        installed_name = added[0].file_name
        CurseForgeManualInstaller._save_mod_file(instance, requirement, installed_name, compatibility_warning)
        return installed_name

    @staticmethod
    def install_many(instance: Instance, requirements: tuple[CurseForgeManualDownload, ...] | list[CurseForgeManualDownload], sources: tuple[Path, ...] | list[Path], launch_lock_token: str | None = None) -> CurseForgeManualImportResult:
        if InstanceRunLock.is_active(instance) and not InstanceRunLock.owns_preparing_lock(instance, launch_lock_token):
            raise RuntimeError("Close Minecraft before adding downloaded files.")

        pending = list(requirements)
        imported: list[CurseForgeManualImportedFile] = []
        extras: list[Path] = []
        rejected: list[str] = []
        seen_sources: set[Path] = set()

        for source_value in sources:
            source = Path(source_value)
            try:
                resolved = source.resolve()
            except OSError:
                resolved = source
            if resolved in seen_sources:
                continue
            seen_sources.add(resolved)

            if not source.is_file():
                rejected.append(f"{source.name}: The selected file is not readable.")
                continue

            size = source.stat().st_size
            digest = CurseForgeManualInstaller._sha1(source)
            requirement = CurseForgeManualInstaller._match_requirement(source, size, digest, pending)
            if requirement is not None:
                try:
                    installed_name = CurseForgeManualInstaller.install(instance, requirement, source, launch_lock_token=launch_lock_token)
                except Exception as error:
                    rejected.append(f"{source.name}: {error}")
                    continue
                imported.append(CurseForgeManualImportedFile(requirement=requirement, installed_name=installed_name))
                pending.remove(requirement)
                continue

            filename_requirement = next((item for item in pending if item.file_name.casefold() == source.name.casefold()), None)
            if filename_requirement is not None:
                rejected.append(
                    f"{source.name}: The filename matches a required CurseForge file, but its size or SHA-1 checksum is different."
                )
                continue

            if source.suffix.casefold() == ".jar":
                extras.append(source)
            else:
                rejected.append(
                    f"{source.name}: This file is not listed by the modpack. Only unmatched .jar files can be added as extra mods."
                )

        added_mod_names: list[str] = []
        for source in extras:
            try:
                added = ModManager.add_mods(instance, [source], replace=False, launch_lock_token=launch_lock_token, allow_unverified=True)
            except Exception as error:
                rejected.append(f"{source.name}: {error}")
                continue
            filenames = [mod.file_name for mod in added]
            ModrinthRegistry.remove_by_filenames(instance, filenames)
            CurseForgeRegistry.remove_by_filenames(instance, filenames)
            added_mod_names.extend(filenames)

        return CurseForgeManualImportResult(
            imported=tuple(imported),
            added_mods=tuple(added_mod_names),
            rejected=tuple(rejected),
        )

    @staticmethod
    def _match_requirement(source: Path, size: int, digest: str, requirements: list[CurseForgeManualDownload]) -> CurseForgeManualDownload | None:
        checksum_matches = [item for item in requirements if item.sha1 and item.sha1.casefold() == digest.casefold()]
        if checksum_matches:
            exact_name = next((item for item in checksum_matches if item.file_name.casefold() == source.name.casefold()), None)
            return exact_name or checksum_matches[0]

        name_matches = [
            item
            for item in requirements
            if not item.sha1
            and item.file_name.casefold() == source.name.casefold()
            and (item.file_size <= 0 or item.file_size == size)
        ]
        return name_matches[0] if len(name_matches) == 1 else None

    @staticmethod
    def _install_pack_file(instance: Instance, requirement: CurseForgeManualDownload, source: Path, allow_while_paused: bool = False) -> str:
        target, relative = CurseForgePackRegistry.managed_path(
            instance,
            requirement.managed_path,
            requirement.file_name,
        )
        artifact_download_service.accept_manual_file(CurseForgeManualInstaller._request(requirement, target), source, allow_while_paused=allow_while_paused)

        compatibility_warning = ""
        if target.suffix.casefold() == ".jar":
            try:
                loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
                metadata = ModManager.read_mod(target, preferred_loader=loader_name)
                compatibility_warning = ModManager.compatibility_warning(instance, metadata)
            except Exception as error:
                compatibility_warning = f"Managed modpack file accepted without loader verification: {error}"

        CurseForgeManualInstaller._save_pack_file(instance, requirement, relative, compatibility_warning)
        return target.name

    @staticmethod
    def _save_pack_file(instance: Instance, requirement: CurseForgeManualDownload, installed_relative: str, compatibility_warning: str) -> None:
        pack = CurseForgePackRegistry.load(instance)
        managed = pack.get("managedFiles", [])
        updated = False
        new_path, safe_relative = CurseForgePackRegistry.managed_path(instance, installed_relative, requirement.file_name)
        for entry in managed:
            if not isinstance(entry, dict):
                continue
            if int(entry.get("projectId") or 0) != requirement.project_id or int(entry.get("fileId") or 0) != requirement.file_id:
                continue
            old_relative = CurseForgePackRegistry.safe_relative_path(
                str(entry.get("path") or requirement.managed_path or ""),
                str(entry.get("fileName") or requirement.file_name),
            )
            old_path, _ = CurseForgePackRegistry.managed_path(instance, old_relative, requirement.file_name)
            if old_path != new_path:
                old_path.unlink(missing_ok=True)
                old_path.with_name(old_path.name + ModManager.DISABLED_SUFFIX).unlink(missing_ok=True)
            entry.update({
                "fileName": new_path.name,
                "path": safe_relative,
                "sha1": requirement.sha1,
                "size": requirement.file_size,
                "pendingDownload": False,
                "lastDownloadError": "",
                "retryableDownload": True,
                "acceptedUnverified": bool(compatibility_warning),
                "compatibilityWarning": compatibility_warning,
                "manualImport": True,
            })
            updated = True
            break
        if not updated:
            new_path.unlink(missing_ok=True)
            raise RuntimeError("The selected file is no longer listed in this CurseForge modpack.")
        pack["lastDownloadFailures"] = [
            item for item in pack.get("lastDownloadFailures", [])
            if not (
                isinstance(item, dict)
                and int(item.get("projectId") or 0) == requirement.project_id
                and int(item.get("fileId") or 0) == requirement.file_id
            )
        ]
        CurseForgePackRegistry.save(instance, pack)

    @staticmethod
    def _save_mod_file(instance: Instance, requirement: CurseForgeManualDownload, installed_name: str, compatibility_warning: str) -> None:
        registry = CurseForgeRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        previous = mods.get(str(requirement.project_id), {}) if isinstance(mods.get(str(requirement.project_id)), dict) else {}
        old_name = str(previous.get("fileName") or "")
        if old_name and old_name.casefold() != installed_name.casefold():
            old_path = CurseForgeRegistry.safe_tracked_path(instance, old_name)
            if old_path is not None:
                old_path.unlink(missing_ok=True)
                old_path.with_name(old_path.name + ModManager.DISABLED_SUFFIX).unlink(missing_ok=True)
        mods[str(requirement.project_id)] = {
            **previous,
            "projectId": requirement.project_id,
            "fileId": requirement.file_id,
            "fileName": installed_name,
            "displayName": requirement.project_name,
            "sha1": requirement.sha1,
            "size": requirement.file_size,
            "downloadUrl": "",
            "source": "curseforge",
            "pendingDownload": False,
            "lastDownloadError": "",
            "retryableDownload": True,
            "acceptedUnverified": bool(compatibility_warning),
            "compatibilityWarning": compatibility_warning,
            "manualImport": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        CurseForgeRegistry.save(instance, registry)

    @staticmethod
    def copy_to_cache(source: Path, destination: Path) -> Path:
        request = ArtifactRequest(provider="curseforge", purpose="manual-cache", destination=destination, expected_filename=destination.name, allow_unverified=True)
        return artifact_download_service.accept_manual_file(request, source)

    @staticmethod
    def _request(requirement: CurseForgeManualDownload, destination: Path) -> ArtifactRequest:
        return ArtifactRequest(
            provider="curseforge",
            purpose="manual-modpack-artifact" if requirement.managed_kind == "pack" else "manual-mod",
            destination=destination,
            urls=(requirement.direct_url,) if requirement.direct_url else (),
            page_url=requirement.version_url,
            project_url=requirement.project_url,
            expected_filename=requirement.file_name,
            expected_size=requirement.file_size,
            hashes={"sha1": requirement.sha1} if requirement.sha1 else {},
            project_id=str(requirement.project_id),
            file_id=str(requirement.file_id),
        )

    @staticmethod
    def _sha1(path: Path) -> str:
        digest = hashlib.sha1(usedforsecurity=False)
        with path.open("rb") as input_file:
            while chunk := input_file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
